"""Preserve the AI appendix across all native Markdown export paths."""

import threading
import re
import hashlib
import json
from datetime import date
from pathlib import Path


REPORT_WRITE_LOCK = threading.RLock()
START = '<!-- daylens-ai-summary:start -->'
END = '<!-- daylens-ai-summary:end -->'


def summary_section(text):
    start = text.find(START)
    end = text.find(END, start)
    if start >= 0 and end >= start:
        return text[start:end + len(END)]
    return ''


def preserve_summary(path, content):
    path = Path(path)
    if path.suffix.lower() != '.md' or START in content or not path.exists():
        return content
    section = summary_section(path.read_text(encoding='utf-8'))
    return content.rstrip() + '\n\n' + section + '\n' if section else content


def attach_summary(path, text, evidence=None):
    from ..exporter import _atomic_write_text
    path = Path(path)
    with REPORT_WRITE_LOCK:
        original = path.read_text(encoding='utf-8') if path.exists() else ''
        if summary_section(original):
            return
        # Model content remains literal text, including possible HTML/links.
        fence = '`' * max(3, max((len(x) for x in re.findall(r'`+', text)), default=0) + 1)
        safe_text = text.replace(START, '').replace(END, '')
        body = f'## 智能汇总\n\n{fence}text\n{safe_text}\n{fence}\n'
        metadata = ''
        if evidence and evidence.get('evidence_fingerprint'):
            from .report_evidence_service import report_dates
            kind, period = evidence['kind'], evidence['period']
            if kind == 'weekly':
                year, week = period.split('-W')
                day = date.fromisocalendar(int(year), int(week), 7)
            elif kind == 'monthly':
                import calendar
                year, month = map(int, period.split('-'))
                day = date(year, month, calendar.monthrange(year, month)[1])
            else:
                day = date.fromisoformat(period)
            identity = {'kind':kind, 'dates':report_dates(kind,day),
                        'fingerprint':evidence['evidence_fingerprint'],
                        'body_hash':hashlib.sha256(body.encode()).hexdigest(),
                        'dependencies':evidence.get('source_reviews',[]),
                        'facts_version':evidence.get('facts_version'),
                        'facts_hash':hashlib.sha256(json.dumps(evidence['facts'],ensure_ascii=False,sort_keys=True).encode()).hexdigest() if 'facts' in evidence else None,
                        'privacy_revision':evidence.get('privacy_revision'),
                        'prompt_hash':evidence.get('prompt_hash')}
            encoded = json.dumps(identity,ensure_ascii=True,separators=(',',':'))
            encoded = encoded.replace('<','\\u003c').replace('>','\\u003e')
            metadata = '<!-- daylens-ai-evidence:'+encoded+' -->\n'
        appendix = f'{START}\n{metadata}{body}{END}'
        _atomic_write_text(str(path), original.rstrip() + '\n\n' + appendix + '\n')
