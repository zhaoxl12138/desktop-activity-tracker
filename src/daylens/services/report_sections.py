"""Preserve the AI appendix across all native Markdown export paths."""

import threading
import re
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


def attach_summary(path, text):
    from ..exporter import _atomic_write_text
    path = Path(path)
    with REPORT_WRITE_LOCK:
        original = path.read_text(encoding='utf-8') if path.exists() else ''
        if summary_section(original):
            return
        # Model content remains literal text, including possible HTML/links.
        fence = '`' * max(3, max((len(x) for x in re.findall(r'`+', text)), default=0) + 1)
        safe_text = text.replace(START, '').replace(END, '')
        appendix = f'{START}\n## 智能汇总\n\n{fence}text\n{safe_text}\n{fence}\n{END}'
        _atomic_write_text(str(path), original.rstrip() + '\n\n' + appendix + '\n')
