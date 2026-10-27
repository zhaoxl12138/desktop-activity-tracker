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
