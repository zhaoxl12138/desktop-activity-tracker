"""Persistent, fail-closed reservations for optional AI calls (CNY micros)."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class BudgetUnavailable(RuntimeError):
    pass


class IntelligenceBudget:
    # Peak tariff, 2026-09-07. One micro-CNY per token at 1 CNY/million.
    INPUT_RATE = 3
    OUTPUT_RATE = 9
    HIT_RATE = 0.1

    def __init__(self, path: str | Path, monthly_micros: int = 4_000_000):
        self.path = Path(path)
        self.monthly_micros = max(0, int(monthly_micros))

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        with lock.open('a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise BudgetUnavailable('AI用量状态正在使用，请稍后再试') from None
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _load(self):
        if not self.path.exists():
            return {'version': 1, 'requests': {}}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data['version'] != 1 or not isinstance(data['requests'], dict):
                raise ValueError()
            for row in data['requests'].values():
                if (type(row['cost_micros']) is not int or row['cost_micros'] < 0
                        or not isinstance(row['month'], str)
                        or not isinstance(row['day'], str)
                        or not isinstance(row['kind'], str)
                        or type(row['units']) is not int or row['units'] < 0
                        or not isinstance(row['state'], str)
                        or row['state'] not in ('reserved', 'settled', 'uncertain')):
                    raise ValueError()
            return data
        except (OSError, ValueError, KeyError, TypeError):
            raise BudgetUnavailable('AI用量记录无法读取，已暂停调用以保护预算') from None

    def _save(self, data):
        fd, name = tempfile.mkstemp(prefix='budget-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(data, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def reserve(self, input_ceiling: int, output_ceiling: int, *, kind='classification',
                units=1, daily_limit=30, now: datetime | None = None,
                idempotency_key: str | None = None) -> str:
        if (type(input_ceiling) is not int or type(output_ceiling) is not int
                or input_ceiling < 0 or output_ceiling < 0
                or type(units) is not int or units < 1
                or (idempotency_key is not None and
                    (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200))):
            raise ValueError('Invalid reservation')
        now = now or datetime.now()
        day, month = now.strftime('%Y-%m-%d'), now.strftime('%Y-%m')
        amount = input_ceiling * self.INPUT_RATE + output_ceiling * self.OUTPUT_RATE
        with self._locked():
            data = self._load()
            rows = data['requests'].values()
            if idempotency_key is not None and any(
                row.get('kind') == kind and row.get('idempotency_key') == idempotency_key
                for row in rows
            ):
                raise BudgetUnavailable('该批任务证据已请求或预留，不重复发送')
            spent = sum(r['cost_micros'] for r in rows if r['month'] == month)
            used = sum(r['units'] for r in rows if r['day'] == day and r['kind'] == kind)
            if spent + amount > self.monthly_micros:
                raise BudgetUnavailable('已达到AI月预算，继续使用本地记录')
            if used + units > daily_limit:
                raise BudgetUnavailable('已达到该功能今日调用上限')
            request_id = uuid.uuid4().hex
            data['requests'][request_id] = {
                'day': day, 'month': month, 'kind': kind, 'units': units,
                'cost_micros': amount, 'reserved_micros': amount, 'state': 'reserved',
            }
            if idempotency_key is not None:
                data['requests'][request_id]['idempotency_key'] = idempotency_key
            self._save(data)
        return request_id

    def settle(self, request_id: str, usage: dict | None):
        with self._locked():
            data = self._load()
            row = data['requests'][request_id]
            if row['state'] != 'reserved':
                return
            valid = isinstance(usage, dict)
            for key in ('prompt_tokens', 'completion_tokens'):
                value = usage.get(key) if valid else None
                if type(value) is not int or value < 0:
                    valid = False
            if valid:
                # Use peak uncached prices until tariff timing/cache accounting is
                # verified. The product shows a conservative estimate, not an invoice.
                row['cost_micros'] = (usage['prompt_tokens'] * self.INPUT_RATE
                                      + usage['completion_tokens'] * self.OUTPUT_RATE)
                row['input_tokens'] = usage['prompt_tokens']
                row['output_tokens'] = usage['completion_tokens']
                row['state'] = 'settled'
            else:
                # Request may have been billed despite timeout/crash. Never refund
                # an uncertain call just because no response reached this process.
                row['state'] = 'uncertain'
            self._save(data)

    def snapshot(self, now: datetime | None = None):
        now = now or datetime.now()
        with self._locked():
            rows = list(self._load()['requests'].values())
        month = [r for r in rows if r['month'] == now.strftime('%Y-%m')]
        day = [r for r in month if r['day'] == now.strftime('%Y-%m-%d')]
        return {
            'cost_micros': sum(r['cost_micros'] for r in month),
            'budget_micros': self.monthly_micros,
            'today_requests': len(day),
            'today_titles': sum(r['units'] for r in day if r['kind'] == 'classification'),
            'uncertain_requests': sum(r['state'] != 'settled' for r in month),
        }
