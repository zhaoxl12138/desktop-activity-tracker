# DayLens Classification Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore content-based classification for Chrome and 360 browsers, prevent unrelated background audio from extending video sessions, and preserve built-in title keywords during first-run rule merges.

**Architecture:** Keep the current classifier pipeline, but make browser recognition a single explicit concept and move `browser_general` behind content matching. Tighten `AudioDetector.is_playing()` to use only the requested PID. Make custom-rule merging inherit built-in title keywords only when the stored custom list is empty.

**Tech Stack:** Python 3.14, PyYAML, SQLite, PySide6, pycaw/comtypes, pytest.

---

### Task 1: Browser content classification precedence

**Files:**
- Create: `tests/test_classifier_integrity.py`
- Modify: `src/daylens/classifier.py:1-130`

- [ ] **Step 1: Write failing browser classification tests**

Create a temporary YAML config containing `video`, `coding`, `browser_general`, and `other`. Include `Chrome` in the generic browser keywords so the test reproduces the current short-circuit.

```python
from pathlib import Path

import yaml

from desktop_activity_tracker.classifier import Classifier


def _write_config(path: Path) -> None:
    config = {
        "categories": {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": [],
                    "title_keywords": ["YouTube", "bilibili"],
                },
            },
            "coding": {
                "display_name": "编程开发",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": [],
                    "title_keywords": ["GitHub"],
                },
            },
            "browser_general": {
                "display_name": "浏览器",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["chrome.exe", "360ChromeX.exe"],
                    "title_keywords": ["Chrome", "浏览器", "新标签页"],
                },
            },
            "other": {
                "display_name": "其他",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        }
    }
    path.write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )


def test_chrome_youtube_uses_content_before_browser_fallback(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "YouTube - Google Chrome",
    )
    assert result["category_key"] == "video"


def test_360_bilibili_uses_content_before_browser_fallback(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    result = Classifier(str(config_path)).classify(
        "360ChromeX.exe",
        "凡人修仙传 - bilibili - 360极速浏览器X",
    )
    assert result["category_key"] == "video"


def test_chrome_github_uses_coding_content_rule(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "GitHub - Google Chrome",
    )
    assert result["category_key"] == "coding"


def test_chrome_new_tab_falls_back_to_browser_general(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "新标签页 - Google Chrome",
    )
    assert result["category_key"] == "browser_general"
```

- [ ] **Step 2: Run tests and verify the content tests fail**

Run:

```powershell
py -m pytest tests/test_classifier_integrity.py -q
```

Expected: the YouTube, bilibili, and GitHub tests fail because the current classifier returns `browser_general`; the new-tab fallback passes.

- [ ] **Step 3: Implement unified browser recognition and precedence**

In `src/daylens/classifier.py`, define the built-in browser process set:

```python
_DEFAULT_BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "iexplore.exe",
    "firefox.exe",
    "msedgewebview2.exe",
    "chromium.exe",
    "brave.exe",
    "vivaldi.exe",
    "opera.exe",
    "360chrome.exe",
    "360chromex.exe",
    "qqbrowser.exe",
    "sogouexplorer.exe",
}
```

During `Classifier.__init__`, combine this set with the configured `browser_general.match.process_names`, lowercasing every value:

```python
browser_match = self.categories.get("browser_general", {}).get("match", {})
self.browser_processes = _DEFAULT_BROWSER_PROCESSES | {
    process.lower()
    for process in browser_match.get("process_names", [])
    if process
}
```

In the first classification pass, skip both `other` and `browser_general`:

```python
if key in ("other", "browser_general"):
    continue
```

Replace the local hard-coded `browser_procs` variable with `self.browser_processes` throughout `classify()`. Use the same set for the generic browser fallback:

```python
if process_name in self.browser_processes:
    return {
        "category_key": "browser_general",
        "category_name": bg.get("display_name", "浏览器"),
        "active_rule": bg.get("active_rule", "interactive_required"),
    }
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```powershell
py -m pytest tests/test_classifier_integrity.py -q
```

Expected: `4 passed`.

### Task 2: PID-scoped audio evidence

**Files:**
- Create: `tests/test_audio_detector.py`
- Modify: `src/daylens/audio_detector.py:31-59`

- [ ] **Step 1: Write a failing test for unrelated background audio**

```python
from desktop_activity_tracker.audio_detector import AudioDetector


def test_missing_target_audio_session_does_not_use_other_process_audio(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(
        "desktop_activity_tracker.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [],
    )
    monkeypatch.setattr(detector, "is_any_playing", lambda: True)

    assert detector.is_playing(12345) is False
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
py -m pytest tests/test_audio_detector.py -q
```

Expected: FAIL because the current no-session path calls `is_any_playing()` and returns `True`.

- [ ] **Step 3: Remove the any-process fallback**

In `AudioDetector.is_playing()`, replace the no-session fallback with:

```python
self._cached = False
```

Keep `is_any_playing()` unchanged as a standalone diagnostic helper.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
py -m pytest tests/test_audio_detector.py -q
```

Expected: `1 passed`.

### Task 3: Preserve built-in title keywords during custom rule merge

**Files:**
- Create: `tests/test_custom_rule_merge.py`
- Modify: `src/daylens/repositories/settings_repository.py:117-131`

- [ ] **Step 1: Write failing merge tests**

```python
from desktop_activity_tracker import database


def _base_config():
    return {
        "categories": {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": ["QyClient.exe"],
                    "title_keywords": ["YouTube", "bilibili"],
                },
            }
        }
    }


def test_empty_custom_title_keywords_inherit_builtins(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    database.save_custom_rules(
        str(db_path),
        {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "process_names": ["QyClient.exe"],
                "title_keywords": [],
            }
        },
    )
    config = _base_config()

    database.merge_custom_rules(config, str(db_path))

    assert config["categories"]["video"]["match"]["title_keywords"] == [
        "YouTube",
        "bilibili",
    ]


def test_nonempty_custom_title_keywords_override_builtins(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    database.save_custom_rules(
        str(db_path),
        {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "process_names": ["QyClient.exe"],
                "title_keywords": ["自定义视频站"],
            }
        },
    )
    config = _base_config()

    database.merge_custom_rules(config, str(db_path))

    assert config["categories"]["video"]["match"]["title_keywords"] == [
        "自定义视频站",
    ]
```

- [ ] **Step 2: Run the tests and verify the inheritance test fails**

Run:

```powershell
py -m pytest tests/test_custom_rule_merge.py -q
```

Expected: the empty-keyword inheritance test fails; the nonempty override test passes.

- [ ] **Step 3: Implement empty-keyword inheritance**

In `merge_custom_rules()`, capture the existing match rule before replacing the category:

```python
base_category = categories.get(key, {})
base_match = base_category.get("match", {}) if isinstance(base_category, dict) else {}
title_keywords = rule["title_keywords"] or list(
    base_match.get("title_keywords", []) or []
)
```

Store `title_keywords` in the merged category while leaving the custom process list and nonempty keyword behavior unchanged.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
py -m pytest tests/test_custom_rule_merge.py -q
```

Expected: `2 passed`.

### Task 4: Full verification and live release

**Files:**
- Verify: `src/daylens/classifier.py`
- Verify: `src/daylens/audio_detector.py`
- Verify: `src/daylens/repositories/settings_repository.py`
- Verify: `tests/test_classifier_integrity.py`
- Verify: `tests/test_audio_detector.py`
- Verify: `tests/test_custom_rule_merge.py`

- [ ] **Step 1: Run all tests**

Run:

```powershell
py -m pytest -q
```

Expected: all tests pass with no failures.

- [ ] **Step 2: Verify classification against the current database**

Run a read-only script using `Classifier("config/config.yaml", "data/usage.db")` and assert:

```python
assert classifier.classify(
    "chrome.exe",
    "YouTube - Google Chrome",
)["category_key"] == "video"
assert classifier.classify(
    "360ChromeX.exe",
    "bilibili - 360极速浏览器X",
)["category_key"] == "video"
assert classifier.classify(
    "chrome.exe",
    "GitHub - Google Chrome",
)["category_key"] == "coding"
```

- [ ] **Step 3: Commit the implementation**

Run:

```powershell
git add src/daylens/classifier.py src/daylens/audio_detector.py src/daylens/repositories/settings_repository.py tests/test_classifier_integrity.py tests/test_audio_detector.py tests/test_custom_rule_merge.py
git commit -m "fix: restore trustworthy content classification"
```

- [ ] **Step 4: Build the release**

Run:

```powershell
py tools/build_release.py
```

Expected: PyInstaller completes successfully, `release/DayLens.exe` exists, and the desktop shortcut is refreshed.

- [ ] **Step 5: Restart and verify DayLens**

Run:

```powershell
Start-Process -FilePath "D:\OfficeSoftware\DayLens\release\DayLens.exe"
Start-Sleep -Seconds 2
Get-CimInstance Win32_Process |
    Where-Object {$_.Name -eq "DayLens.exe"} |
    Select-Object ProcessId, ExecutablePath
```

Expected: one DayLens process running from `D:\OfficeSoftware\DayLens\release\DayLens.exe`.

