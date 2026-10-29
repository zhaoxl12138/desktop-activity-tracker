"""Decide whether one classification may become an application-wide rule."""

from __future__ import annotations

from ..classifier import _DEFAULT_BROWSER_PROCESSES


_MULTIPURPOSE_PROCESSES = {
    "wps.exe", "wpspdf.exe", "winword.exe", "excel.exe", "powerpnt.exe",
    "explorer.exe", "applicationframehost.exe", "code.exe", "python.exe",
}
_AUTO_PROCESS_CATEGORIES = {"gaming"}


def choose_learning_scope(
    process_name: str,
    category_key: str,
    *,
    source: str,
    requested_scope: str = "similar",
) -> str:
    """Return ``process`` only when application-wide learning is justified."""
    process = str(process_name or "").strip().casefold()
    requested = str(requested_scope or "similar").strip().casefold()
    if process in _DEFAULT_BROWSER_PROCESSES or process in _MULTIPURPOSE_PROCESSES:
        return "title"
    if requested == "process" and source == "manual":
        return "process"
    if str(category_key or "") in _AUTO_PROCESS_CATEGORIES:
        return "process"
    return "title"
