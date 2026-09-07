"""Nonblocking classifier queue: active-time eligibility and durable local reuse."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from .intelligence_budget import IntelligenceBudget
from .intelligence_client import DeepSeekProvider, LEGAL_CATEGORIES
from .intelligence_credentials import read_key
from .intelligence_state import DEFAULT_SETTINGS, atomic_json, load_overrides, load_settings, title_context


class IntelligenceScheduler:
    def __init__(self, directory, *, provider=None, clock=time.monotonic):
        self.directory = Path(directory)
        self.clock = clock
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wakeup = threading.Event()
        self.settings = load_settings(directory)
        self.budget = IntelligenceBudget(self.directory / 'budget.json',
                                         self.settings['monthly_budget_micros'])
        self.provider = provider or DeepSeekProvider(self.budget, read_key)
        self.key_available = bool(getattr(self.provider, 'key_reader', lambda: True)())
        self.pending = OrderedDict()
        self.active = OrderedDict()
        self.attempted = set()
        self.day = datetime.now().date()
        self.generation = 0
        self.error = ''
        self.cache = self._load_cache()
        self.overrides = load_overrides(directory)
        self.thread = None
        self.current_identity = None

    def _load_cache(self):
        path = self.directory / 'classification_cache.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return {}
            valid = {}
            for key, value in data.items():
                if (isinstance(key, str) and isinstance(value, dict)
                        and isinstance(value.get('category'), str)
                        and value['category'] in LEGAL_CATEGORIES
                        and value.get('certainty') in ('high', 'medium', 'low', 'conflict')
                        and isinstance(value.get('reason'), str)
                        and len(value['reason']) <= 80):
                    valid[key] = value
            return valid
        except (OSError, ValueError, TypeError):
            return {}

    def start(self):
        if self.thread is not None:
            return
        # Pure Python thread, never owns QObjects or recording/audio resources.
        self.thread = threading.Thread(target=self._run, name='DayLens-AI', daemon=True)
        self.thread.start()

    def reload(self):
        settings = load_settings(self.directory)
        overrides = load_overrides(self.directory)
        key_available = bool(getattr(self.provider, 'key_reader', lambda: True)())
        with self.lock:
            self.generation += 1
            self.settings = settings
            self.overrides = overrides
            self.key_available = key_available
            self.budget.monthly_micros = settings['monthly_budget_micros']
            self.pending.clear()
            self.active.clear()
            self.current_identity = None
        self.wakeup.set()

    def close(self):
        with self.lock:
            self.generation += 1
            self.stop_event.set()
            self.pending.clear()
        self.wakeup.set()
        if self.thread is not None:
            self.thread.join(timeout=0.1)

    def observe(self, process, title, base_category, rule_version, *, active_seconds=0):
        """Called on sampling thread. No disk/network operations here."""
        with self.lock:
            manual_context = title_context(process, title, dict(DEFAULT_SETTINGS), 'manual-v1')
            if manual_context and manual_context['id'] in self.overrides:
                return dict(self.overrides[manual_context['id']])
            if not self.settings['enabled'] or not self.settings['classification_enabled'] or not self.key_available:
                self.current_identity = None
                return None
            if base_category not in ('browser_general', 'other'):
                self.current_identity = None
                return None
            context = title_context(process, title, self.settings, rule_version)
            if context is None:
                self.current_identity = None
                return None
            identity = context['id']
            self.current_identity = identity
            if identity in self.cache:
                return dict(self.cache[identity])
            if self.day != datetime.now().date():
                self.day = datetime.now().date()
                self.attempted.clear()
                self.active.clear()
                self.pending.clear()
            if identity in self.attempted:
                return None
            self.active[identity] = self.active.get(identity, 0) + max(0, min(5, active_seconds))
            self.active.move_to_end(identity)
            if len(self.active) > 256:
                self.active.popitem(last=False)
            if self.active[identity] >= 30 and identity not in self.pending and len(self.pending) < 30:
                self.pending[identity] = (context, self.clock())
                self.wakeup.set()
            return None

    def process_pending(self, *, force=False):
        """Worker-side one-batch operation, also deterministically testable."""
        with self.lock:
            if (self.stop_event.is_set() or not self.settings['enabled']
                    or not self.settings['classification_enabled'] or not self.key_available or not self.pending):
                return
            first_time = next(iter(self.pending.values()))[1]
            if not force and len(self.pending) < 5 and self.clock() - first_time < 15:
                return
            batch = [self.pending.popitem(last=False)[1][0] for _ in range(min(5, len(self.pending)))]
            self.attempted.update(c['id'] for c in batch)
            generation = self.generation
        try:
            result = self.provider.classify(batch)
            if not isinstance(result, dict):
                return
            with self.lock:
                if generation != self.generation or self.stop_event.is_set():
                    return
                # Late results are cached by immutable title identity; they are
                # never pushed onto the current session from this thread.
                for context in batch:
                    if context['id'] in result:
                        result[context['id']]['context'] = context
                self.cache.update(result)
                self.error = ''
                saved = dict(self.cache)
            atomic_json(self.directory / 'classification_cache.json', saved)
        except Exception:
            with self.lock:
                self.error = 'AI请求未完成，继续使用本地分类；请检查连接与预算'

    def _run(self):
        while not self.stop_event.is_set():
            self.wakeup.wait(timeout=1)
            self.wakeup.clear()
            try:
                self.process_pending()
            except Exception:
                with self.lock:
                    self.error = 'AI任务异常，继续使用本地分类'
