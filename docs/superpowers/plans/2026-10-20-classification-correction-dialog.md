# Classification Correction Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unreliable system classification prompts with one testable DayLens dialog and allow an existing learned title pattern to be reclassified in place.

**Architecture:** Put category presentation and selection in a focused `ClassificationDialog` widget, keep persistence in `intelligence_evidence`, and let `LiveMonitorPage` only orchestrate the selected sample or pattern. Exact corrections continue through `save_override`; learned-pattern category changes use an atomic service operation that preserves pattern identity and usage metadata.

**Tech Stack:** Python 3.14, PySide6, JSON state files, pytest, PyInstaller.

## Execution record — 2026-10-20

- Implementation committed as `a0da2e9` on `main`.
- Five new regression tests include actual Qt modal save/cancel clicks and the complete three-dialog pattern-edit flow, using temporary state directories.
- Full suite: 933 passed. `python tests/test_gui_smoke.py`, `compileall`, diff validation, and packaged Qt smoke passed.
- Dialog rendering verified with Microsoft YaHei loaded for offscreen screenshots.
- Canonical release updated after a successful maintenance shutdown. Previous release retained at `release_backup_20261020_correction`; database remains `data/usage.db`.
- Native desktop UI click verification could not finish: Windows screenshot capture timed out and accessibility clicks returned `coordinate input geometry is unavailable`. Packaged app startup, main-window accessibility, and continued sampling were verified; automated dialog interactions ran against the source widgets, not the packaged native window.
- Existing unrelated changes in `today_overview.py` and `test_top_app_icons.py` were preserved.

---

## File structure

- Create `src/daylens/gui/widgets/classification_dialog.py`: canonical category choices and the styled modal dialog.
- Modify `src/daylens/services/intelligence_evidence.py`: atomically change an existing pattern category without recreating it.
- Modify `src/daylens/gui/pages/live_monitor.py`: replace `QInputDialog` correction flows, add visible feedback, and connect pattern reclassification.
- Create `tests/test_classification_dialog.py`: offscreen widget behavior and category completeness.
- Modify `tests/test_intelligence_evidence.py`: persistence regression tests for in-place updates.
- Create `tests/test_live_monitor_correction.py`: orchestration tests for no-sample, current-title correction, and pattern editing.

### Task 1: Add the reusable classification dialog

**Files:**
- Create: `tests/test_classification_dialog.py`
- Create: `src/daylens/gui/widgets/classification_dialog.py`

- [ ] **Step 1: Write failing dialog tests**

```python
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from daylens.gui.widgets.classification_dialog import CATEGORY_CHOICES, ClassificationDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_dialog_lists_every_supported_category_and_selects_current_value():
    _app()
    dialog = ClassificationDialog(
        app_name='chrome.exe', title='学习中心', current_category='reading')
    assert set(dict(CATEGORY_CHOICES).values()) == {
        'coding', 'reading', 'office', 'ai_tools', 'creative', 'social',
        'tools', 'gaming', 'video', 'browser_general', 'other',
    }
    assert dialog.selected_category() == 'reading'
    assert 'chrome.exe' in dialog.app_label.text()
    assert '学习中心' in dialog.title_label.text()


def test_dialog_can_select_another_category_by_value():
    _app()
    dialog = ClassificationDialog(
        app_name='chrome.exe', title='电影', current_category='browser_general')
    index = dialog.category_combo.findData('video')
    dialog.category_combo.setCurrentIndex(index)
    assert dialog.selected_category() == 'video'
    assert dialog.media_hint.isVisibleTo(dialog) is False
    dialog.show()
    QApplication.processEvents()
    assert dialog.media_hint.isVisible()
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_classification_dialog.py -q`

Expected: collection fails because `daylens.gui.widgets.classification_dialog` does not exist.

- [ ] **Step 3: Implement the focused dialog**

Create `classification_dialog.py` with a tuple of `(display_name, category_key)` values and a `QDialog` containing escaped plain-text labels, a styled `QComboBox`, a media warning label, and `QDialogButtonBox(Cancel | Save)`. Apply `ui_style.get_input_style()` plus an explicit `QComboBox QAbstractItemView` background/text rule so the popup remains legible in both themes. Expose only:

```python
CATEGORY_CHOICES = (
    ('技术学习 / 开发', 'coding'), ('阅读学习', 'reading'),
    ('办公 / 求职', 'office'), ('AI工具', 'ai_tools'),
    ('设计创作', 'creative'), ('社交通讯', 'social'),
    ('系统工具', 'tools'), ('游戏娱乐', 'gaming'),
    ('影音娱乐', 'video'), ('浏览器', 'browser_general'), ('其他', 'other'),
)

class ClassificationDialog(QDialog):
    def __init__(self, *, app_name, title, current_category, parent=None): ...
    def selected_category(self) -> str: ...
```

Connect `currentIndexChanged` so the warning text is visible only for `video` and reads “影音分类可能影响后续被动播放计时”。

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `python -m pytest tests/test_classification_dialog.py -q`

Expected: 2 passed.

- [ ] **Step 5: Commit the dialog**

```powershell
git add src/daylens/gui/widgets/classification_dialog.py tests/test_classification_dialog.py
git commit -m "fix: add reliable classification chooser"
```

### Task 2: Support in-place learned-pattern reclassification

**Files:**
- Modify: `tests/test_intelligence_evidence.py`
- Modify: `src/daylens/services/intelligence_evidence.py`

- [ ] **Step 1: Write failing service tests**

```python
from daylens.services.intelligence_evidence import update_pattern_category


def test_update_pattern_category_preserves_identity_and_usage_metadata(tmp_path):
    saved = save_pattern(tmp_path, 'chrome.exe', '学习中心 视频课程', 'reading')
    patterns = load_patterns(tmp_path)
    patterns[0]['hit_count'] = 7
    patterns[0]['last_used_at'] = '2026-10-20T10:00:00'
    from daylens.services.intelligence_evidence import save_patterns
    save_patterns(tmp_path, patterns)

    assert update_pattern_category(tmp_path, saved['id'], 'video') is True
    changed = load_patterns(tmp_path)[0]
    assert changed['id'] == saved['id']
    assert changed['category'] == 'video'
    assert changed['hit_count'] == 7
    assert changed['last_used_at'] == '2026-10-20T10:00:00'
    assert changed['created_at'] == saved['created_at']


def test_update_pattern_category_rejects_invalid_category_without_writing(tmp_path):
    saved = save_pattern(tmp_path, 'chrome.exe', '学习中心 视频课程', 'reading')
    before = (tmp_path / 'title_patterns.json').read_bytes()
    import pytest
    with pytest.raises(ValueError, match='不支持的分类'):
        update_pattern_category(tmp_path, saved['id'], 'not-real')
    assert (tmp_path / 'title_patterns.json').read_bytes() == before
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_intelligence_evidence.py -q`

Expected: import fails because `update_pattern_category` is missing.

- [ ] **Step 3: Implement the atomic update**

Add:

```python
def update_pattern_category(directory, pattern_id: str, category: str) -> bool:
    if category not in LEGAL_CATEGORIES:
        raise ValueError('不支持的分类')
    patterns = load_patterns(directory)
    changed = False
    for row in patterns:
        if row.get('id') == pattern_id:
            if row.get('category') != category:
                row['category'] = category
                changed = True
            else:
                return True
    if not changed:
        return False
    save_patterns(directory, patterns)
    return True
```

- [ ] **Step 4: Run evidence tests and verify GREEN**

Run: `python -m pytest tests/test_intelligence_evidence.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the service change**

```powershell
git add src/daylens/services/intelligence_evidence.py tests/test_intelligence_evidence.py
git commit -m "fix: reclassify learned title patterns in place"
```

### Task 3: Repair both live-monitor correction flows

**Files:**
- Create: `tests/test_live_monitor_correction.py`
- Modify: `src/daylens/gui/pages/live_monitor.py`

- [ ] **Step 1: Write failing orchestration tests**

Use an offscreen `QApplication`, monkeypatch `LiveMonitorPage._review_directory` to `tmp_path`, and monkeypatch `ClassificationDialog.exec`/`selected_category` so tests exercise real persistence without opening a blocking modal. Cover these behaviors:

```python
def test_correct_current_without_sample_shows_visible_feedback(...):
    page = LiveMonitorPage()
    page._correct_current()
    assert '暂无可纠正' in page.correction_status.text()


def test_correct_current_persists_selected_category_and_emits_reload(...):
    page = LiveMonitorPage()
    page._samples = [{'process_name': 'chrome.exe', 'window_title': '学习中心',
                      'category_key': 'browser_general'}]
    # Accepted fake dialog returns reading.
    page._correct_current()
    assert next(iter(load_overrides(tmp_path).values()))['category'] == 'reading'
    assert signal_count == 1
    assert '已纠正为' in page.correction_status.text()


def test_manage_pattern_can_change_category_without_changing_id(...):
    original = save_pattern(tmp_path, 'chrome.exe', '学习中心 视频课程', 'reading')
    # Select the only pattern, choose 修改分类, accepted fake dialog returns video.
    page._manage_patterns()
    changed = load_patterns(tmp_path)[0]
    assert changed['id'] == original['id']
    assert changed['category'] == 'video'
    assert signal_count == 1
```

Also verify cancel paths do not mutate files, deletion calls a confirmation dialog, and both flows pass the existing category into the chooser.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_live_monitor_correction.py -q`

Expected: failures show that there is no `correction_status`, the current flow still uses `QInputDialog`, and pattern actions do not include modification.

- [ ] **Step 3: Replace current-title correction**

In `LiveMonitorPage`:

- Add a muted `correction_status` label beside the two action buttons.
- Remove the video hard stop and all local category dictionaries.
- Instantiate `ClassificationDialog` with the sample app, title, and `category_key`.
- On acceptance, call `save_override`, emit `classification_corrected`, and set a success message naming the selected display category.
- On no samples, set `correction_status` to “暂无可纠正的前台记录”.
- On failure, include `str(exc)` in the warning and keep the old classification unchanged.

- [ ] **Step 4: Add pattern modification to the manager**

Keep the first pattern picker temporarily, but extend the operation list to `[修改分类, toggle, 删除]`. For modification, open `ClassificationDialog` with pattern app/example/category and call `update_pattern_category`. For deletion, require `QMessageBox.question(... Yes | No)` before `delete_pattern`. Set visible success feedback and emit `classification_corrected` only after an actual operation succeeds.

- [ ] **Step 5: Run live-monitor tests and verify GREEN**

Run: `python -m pytest tests/test_live_monitor_correction.py tests/test_classification_dialog.py tests/test_intelligence_evidence.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit the repaired flows**

```powershell
git add src/daylens/gui/pages/live_monitor.py tests/test_live_monitor_correction.py
git commit -m "fix: repair classification correction workflows"
```

### Task 4: Regression, packaged simulation, and canonical release

**Files:**
- Verify: `src/daylens/gui/widgets/classification_dialog.py`
- Verify: `src/daylens/gui/pages/live_monitor.py`
- Verify: `src/daylens/services/intelligence_evidence.py`
- Build: `tools/build_release.py`

- [ ] **Step 1: Run focused and full verification**

```powershell
python -m pytest tests/test_classification_dialog.py tests/test_live_monitor_correction.py tests/test_intelligence_evidence.py -q
python -m pytest -q
python -m compileall -q src
git diff --check
```

Expected: focused tests pass, full suite passes, compilation exits 0, and diff check prints nothing.

- [ ] **Step 2: Build a staging release without interrupting recording**

Run: `python tools/build_release.py --stage-only`

Expected: PyInstaller and bundled startup smoke both succeed while the existing canonical process continues recording.

- [ ] **Step 3: Replace the canonical release safely**

Request the running DayLens process to exit through the existing maintenance path, verify it stopped, move the previous release to a timestamped recoverable backup, promote staging to `D:\OfficeSoftware\DayLens\release`, and start only `D:\OfficeSoftware\DayLens\release\DayLens.exe`. Do not touch `D:\OfficeSoftware\DayLens\data\usage.db`.

- [ ] **Step 4: Simulate both packaged UI flows**

In the released app:

1. Open “实时监控”, choose “纠正当前分类”, select a different category, save, and verify the visible success message plus creation of `manual_decisions.json`.
2. Open “管理已确认模式”, select the resulting pattern, choose “修改分类”, save a second category, and verify the same pattern ID remains in `title_patterns.json` with the new category.
3. Restore the test-created correction to its original category or delete only the synthetic test pattern if a synthetic title was used; never rewrite ordinary historical records.

Expected: both dialogs are legible and operable, persistence is correct, and the worker reloads without restarting.

- [ ] **Step 5: Verify the single runtime path and commit final integration**

Verify exactly one `DayLens.exe` process and that its executable path is `D:\OfficeSoftware\DayLens\release\DayLens.exe`. Verify the canonical database remains `D:\OfficeSoftware\DayLens\data\usage.db`.

```powershell
git status --short
git log -5 --oneline
```

Do not stage the user's pre-existing modifications in `today_overview.py`, `test_top_app_icons.py`, backups, or temporary files.
