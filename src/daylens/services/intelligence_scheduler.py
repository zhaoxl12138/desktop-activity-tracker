"""Nonblocking classifier queue: active-time eligibility and durable local reuse."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from .intelligence_budget import IntelligenceBudget
from .intelligence_client import DeepSeekProvider, LEGAL_CATEGORIES
from .intelligence_credentials import read_key
from .intelligence_state import DEFAULT_SETTINGS, atomic_json, load_overrides, load_settings, title_context
from .intelligence_evidence import (
    ReviewQueue, load_patterns, match_pattern, redact_title, save_patterns,
)


_AI_CATEGORIES = frozenset(LEGAL_CATEGORIES - {'browser_general', 'other'})
_MEDIA_CATEGORIES = frozenset({'video'})


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
        self.patterns = load_patterns(directory)
        self._patterns_dirty = False
        self.reviews = ReviewQueue(directory)
        self.recent_by_app = {}
        self.thread = None
        self.current_identity = None

    @staticmethod
    def _pending_decision(reason=''):
        return {
            'status': 'pending',
            'source': 'AI待识别',
            'category': '',
            'certainty': '',
            'reason': reason,
            'suggested_category': '',
            'evidence': [],
            'pattern_id': '',
            'apply': False,
        }

    @staticmethod
    def _manual_decision(value):
        category = str(value.get('category') or '')
        return {
            'status': 'applied', 'source': value.get('source', '手动'),
            'category': category, 'suggested_category': category,
            'certainty': 'high', 'reason': value.get('reason', '用户指定分类'),
            'evidence': ['manual_exact'], 'pattern_id': '', 'apply': True,
        }

    def _record_recent(self, process, title, active_seconds, confirmed_category=''):
        app = str(process or '').strip().casefold()
        safe_title = redact_title(title)
        if not app or not safe_title:
            return
        now = self.clock()
        rows = [row for row in self.recent_by_app.get(app, [])
                if now - row['_seen'] <= 600 and row['title'] != safe_title]
        previous = next((row for row in self.recent_by_app.get(app, [])
                         if row['title'] == safe_title and now - row['_seen'] <= 600), None)
        seconds = max(0, min(5, int(active_seconds or 0)))
        rows.append({
            'app': app[:80], 'title': safe_title,
            'active_seconds': min(3600, int((previous or {}).get('active_seconds', 0)) + seconds),
            'confirmed_category': confirmed_category or str((previous or {}).get('confirmed_category', '')),
            '_seen': now,
        })
        self.recent_by_app[app] = rows[-5:]

    def _recent_context(self, process):
        app = str(process or '').strip().casefold()
        now = self.clock()
        rows = [row for row in self.recent_by_app.get(app, []) if now - row['_seen'] <= 600]
        return [{key: row[key] for key in ('app', 'title', 'active_seconds', 'confirmed_category')}
                for row in rows[-5:]]

    @staticmethod
    def _confirmed_support(context, category):
        return any(row.get('confirmed_category') == category
                   for row in context.get('recent_titles', []))

    def _decorate_ai_decision(self, context, value):
        category = str(value.get('category') or '')
        certainty = str(value.get('certainty') or '')
        evidence = []
        apply = category in _AI_CATEGORIES and certainty == 'high'
        if (category in _AI_CATEGORIES and category not in _MEDIA_CATEGORIES
                and certainty == 'medium' and self._confirmed_support(context, category)):
            apply = True
            evidence.append('recent_confirmed')
        if certainty == 'high':
            evidence.append('ai_high')
        source = 'AI' if apply else 'AI待确认'
        return {
            'status': 'applied' if apply else 'review',
            'source': source,
            'category': category,
            'suggested_category': category,
            'certainty': certainty,
            'reason': str(value.get('reason') or '')[:80],
            'evidence': evidence,
            'pattern_id': '',
            'apply': apply,
        }

    def _load_cache(self):
        path = self.directory / 'classification_cache.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return {}
            valid = {}
            cutoff = datetime.now() - timedelta(days=180)
            for key, value in data.items():
                if (isinstance(key, str) and isinstance(value, dict)
                        and isinstance(value.get('category'), str)
                        and value['category'] in LEGAL_CATEGORIES
                        and value.get('certainty') in ('high', 'medium', 'low', 'conflict')
                        and isinstance(value.get('reason'), str)
                        and len(value['reason']) <= 80):
                    cached_at = value.get('cached_at')
                    if isinstance(cached_at, str):
                        try:
                            if datetime.fromisoformat(cached_at) < cutoff:
                                continue
                        except ValueError:
                            continue
                    valid[key] = value
            ordered = sorted(
                valid.items(),
                key=lambda item: str(item[1].get('last_used_at') or item[1].get('cached_at') or ''),
            )
            return dict(ordered[-1000:])
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
            self.patterns = load_patterns(self.directory)
            self.reviews = ReviewQueue(self.directory)
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
        self._flush_patterns()

    def _flush_patterns(self):
        with self.lock:
            if not self._patterns_dirty:
                return
            snapshot = [dict(row) for row in self.patterns]
            self._patterns_dirty = False
        save_patterns(self.directory, snapshot)

    def observe(self, process, title, base_category, rule_version, *, active_seconds=0):
        """Called on sampling thread. No disk/network operations here."""
        with self.lock:
            manual_context = title_context(process, title, dict(DEFAULT_SETTINGS), 'manual-v1')
            if manual_context and manual_context['id'] in self.overrides:
                decision = self._manual_decision(self.overrides[manual_context['id']])
                self._record_recent(process, title, active_seconds, decision['category'])
                return decision
            pattern = match_pattern(self.patterns, process, title)
            if pattern is not None:
                for row in self.patterns:
                    if row.get('id') == pattern['pattern_id']:
                        row['hit_count'] = int(row.get('hit_count') or 0) + 1
                        row['last_used_at'] = datetime.now().isoformat(timespec='seconds')
                        self._patterns_dirty = True
                        self.wakeup.set()
                        break
                self._record_recent(process, title, active_seconds, pattern['category'])
                return pattern
            self._record_recent(
                process, title, active_seconds,
                base_category if base_category not in ('browser_general', 'other') else '',
            )
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
            context['base_category'] = base_category
            context['manual_id'] = manual_context['id'] if manual_context else ''
            context['recent_titles'] = self._recent_context(process)
            self.current_identity = identity
            if identity in self.cache:
                self.cache[identity]['last_used_at'] = datetime.now().isoformat(timespec='seconds')
                return self._decorate_ai_decision(context, self.cache[identity])
            if self.day != datetime.now().date():
                self.day = datetime.now().date()
                self.attempted.clear()
                self.active.clear()
                self.pending.clear()
            if identity in self.attempted:
                return self._pending_decision(self.error)
            self.active[identity] = self.active.get(identity, 0) + max(0, min(5, active_seconds))
            self.active.move_to_end(identity)
            if len(self.active) > 256:
                self.active.popitem(last=False)
            if self.active[identity] >= 30 and identity not in self.pending and len(self.pending) < 30:
                context['active_seconds'] = int(self.active[identity])
                self.pending[identity] = (context, self.clock())
                self.wakeup.set()
            return self._pending_decision(self.error)

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
            result = self.provider.classify([
                {key: value for key, value in context.items() if key != 'manual_id'}
                for context in batch
            ])
            if not isinstance(result, dict):
                return
            with self.lock:
                if generation != self.generation or self.stop_event.is_set():
                    return
                # Late results are cached by immutable title identity; they are
                # never pushed onto the current session from this thread.
                review_rows = []
                for context in batch:
                    if context['id'] in result:
                        now_text = datetime.now().isoformat(timespec='seconds')
                        result[context['id']]['cached_at'] = now_text
                        result[context['id']]['last_used_at'] = now_text
                        result[context['id']]['context'] = {
                            key: context[key]
                            for key in ('id', 'app', 'title', 'base_category')
                        }
                        decision = self._decorate_ai_decision(context, result[context['id']])
                        if not decision['apply'] and decision['category'] in _AI_CATEGORIES:
                            review_rows.append({**context, **decision})
                self.cache.update(result)
                if len(self.cache) > 1000:
                    ordered = sorted(
                        self.cache.items(),
                        key=lambda item: str(item[1].get('last_used_at')
                                             or item[1].get('cached_at') or ''),
                    )
                    self.cache = dict(ordered[-1000:])
                self.error = ''
                saved = dict(self.cache)
            for review in review_rows:
                self.reviews.upsert(review)
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
                self._flush_patterns()
            except Exception:
                with self.lock:
                    self.error = 'AI任务异常，继续使用本地分类'
