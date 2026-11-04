from pathlib import Path
import pytest
from daylens import exporter


@pytest.mark.parametrize('name,year,month', [
    ('2026-10-26.md','2026','2026-10'),
    ('2026-09-28_2026-10-04_weekly.md','2026','2026-10'),
    ('2026-12-28_2027-01-03_weekly.md','2027','2027-01'),
    ('2026-09_monthly.md','2026','2026-09'),
])
@pytest.mark.parametrize('configured', ['root','year','month'])
def test_sync_creates_calendar_folders_without_duplicate_years(tmp_path, name, year, month, configured):
    root = tmp_path/'vault'/'reports'
    output = root if configured == 'root' else root/'2026' if configured == 'year' else root/'2026'/'2026-10'
    source = tmp_path/name
    source.write_text('synthetic report', encoding='utf-8')
    result = exporter.sync_to_obsidian(str(source), str(output))
    assert Path(result) == root/year/month/name
    assert Path(result).read_text(encoding='utf-8') == 'synthetic report'
    assert source.exists()
    source.write_text('updated', encoding='utf-8')
    assert exporter.sync_to_obsidian(str(source), str(output)) == result
    assert Path(result).read_text(encoding='utf-8') == 'updated'
    if output/name != Path(result):
        assert not (output/name).exists()


def test_sync_keeps_unknown_names_compatible_and_handles_same_file(tmp_path):
    file = tmp_path/'manual.md'
    file.write_text('unchanged', encoding='utf-8')
    assert exporter.sync_to_obsidian(str(file), str(tmp_path)) == str(file)
    assert file.read_text(encoding='utf-8') == 'unchanged'


def test_sync_failure_preserves_existing_report(tmp_path, monkeypatch):
    import shutil
    root = tmp_path/'vault'
    destination = root/'2026'/'2026-10'/'2026-10-26.md'
    destination.parent.mkdir(parents=True)
    destination.write_text('original', encoding='utf-8')
    source = tmp_path/'2026-10-26.md'
    source.write_text('new', encoding='utf-8')
    def fail(*args, **kwargs):
        raise OSError('synthetic copy error')
    monkeypatch.setattr(shutil, 'copy2', fail)
    assert exporter.sync_to_obsidian(str(source), str(root)) is None
    assert destination.read_text(encoding='utf-8') == 'original'
    assert list(destination.parent.iterdir()) == [destination]


def test_report_service_propagates_sync_failure(tmp_path, monkeypatch):
    from daylens.services.reports_service import sync_report_to_obsidian
    source = tmp_path / '2026-10-28.md'
    source.write_text('native report', encoding='utf-8')
    def fail(*_a, **_k):
        raise PermissionError('cannot write destination')
    monkeypatch.setattr(exporter.shutil, 'copy2', fail)
    with pytest.raises(PermissionError):
        sync_report_to_obsidian(str(source), str(tmp_path / 'vault'))
    assert source.read_text(encoding='utf-8') == 'native report'


def test_report_service_rejects_missing_sync_source(tmp_path):
    from daylens.services.reports_service import sync_report_to_obsidian
    with pytest.raises(FileNotFoundError):
        sync_report_to_obsidian(str(tmp_path / 'missing.md'), str(tmp_path / 'vault'))


def test_strict_exporter_never_succeeds_with_a_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        exporter.sync_to_obsidian(str(tmp_path / 'missing.md'), str(tmp_path / 'vault'), strict=True)


def test_slow_sync_cannot_overwrite_a_newer_native_copy(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import shutil
    import threading

    source = tmp_path / '2026-10-28.md'
    source.write_text('old native report', encoding='utf-8')
    vault = str(tmp_path / 'vault')
    copied, release = threading.Event(), threading.Event()
    original_copy = shutil.copy2

    def copy_and_pause(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        if threading.current_thread().name.startswith('old-sync'):
            copied.set()
            release.wait(2)
        return result

    monkeypatch.setattr(shutil, 'copy2', copy_and_pause)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='old-sync') as pool:
        old = pool.submit(exporter.sync_to_obsidian, str(source), vault, strict=True)
        try:
            assert copied.wait(1)
            replacement = tmp_path / 'replacement.md'
            replacement.write_text('new native report', encoding='utf-8')
            replacement.replace(source)
            destination = Path(exporter.sync_to_obsidian(str(source), vault, strict=True))
        finally:
            release.set()
        with pytest.raises(OSError, match='报告已更新'):
            old.result(timeout=2)
    assert destination.read_text(encoding='utf-8') == 'new native report'


def test_gui_and_cli_publication_do_not_interleave(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    if os.name != 'nt':
        pytest.skip('DayLens Windows publication lock')
    source = tmp_path / '2026-10-28.md'
    source.write_text('old native', encoding='utf-8')
    vault = tmp_path / 'vault'
    destination = vault / '2026' / '2026-10' / source.name
    staged = tmp_path / 'child-staged'
    publishing, release = threading.Event(), threading.Event()
    original_replace = os.replace

    def pause_replace(src, dst):
        if Path(dst) == destination and threading.current_thread().name.startswith('gui-sync'):
            publishing.set()
            release.wait(5)
        return original_replace(src, dst)

    child_code = '''
import sys, shutil
from pathlib import Path
sys.path.insert(0, 'src')
from daylens import exporter
original = shutil.copy2
def copy(*args, **kwargs):
    result = original(*args, **kwargs)
    Path(sys.argv[3]).touch()
    return result
shutil.copy2 = copy
exporter.sync_to_obsidian(sys.argv[1], sys.argv[2], strict=True)
'''
    monkeypatch.setattr(os, 'replace', pause_replace)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='gui-sync') as pool:
        old = pool.submit(exporter.sync_to_obsidian, str(source), str(vault), strict=True)
        child = None
        try:
            assert publishing.wait(1)
            replacement = tmp_path / 'replacement.md'
            replacement.write_text('new native', encoding='utf-8')
            replacement.replace(source)
            child = subprocess.Popen(
                [sys.executable, '-c', child_code, str(source), str(vault), str(staged)],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            deadline = time.monotonic() + 3
            while not staged.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            assert staged.exists()
            with pytest.raises(subprocess.TimeoutExpired):
                child.wait(timeout=.5)
        finally:
            release.set()
            if child is not None:
                assert child.wait(timeout=5) == 0
        assert old.result(timeout=3) == str(destination)
    assert destination.read_text(encoding='utf-8') == 'new native'
