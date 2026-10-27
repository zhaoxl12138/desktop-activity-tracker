import json
import os
import subprocess
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'tools'/'organize_obsidian_reports.ps1'


@pytest.mark.skipif(os.name != 'nt', reason='Windows native recoverable file operations')
def test_organizer_preview_then_keep_newer_and_backup_before_recycling(tmp_path):
    year = tmp_path/'vault'/'2026'
    month = year/'2026-09'
    month.mkdir(parents=True)
    old = month/'2026-09-01.md'
    old.write_text('older snapshot', encoding='utf-8')
    os.utime(old, (1000000000, 1000000000))
    latest = year/'2026-09-01.md'
    latest.write_text('latest snapshot', encoding='utf-8')
    unique = year/'2026-10-26.md'
    unique.write_text('today', encoding='utf-8')
    unknown = year/'manual-note.md'
    unknown.write_text('leave me', encoding='utf-8')
    plan = tmp_path/'plan.json'
    backup = tmp_path/'backup'
    command = ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(SCRIPT),
               '-Root',str(year),'-PlanPath',str(plan)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert old.read_text(encoding='utf-8') == 'older snapshot'
    assert latest.exists() and unique.exists() and not backup.exists()
    manifest = json.loads(plan.read_text(encoding='utf-8-sig'))
    assert manifest['Summary']['Duplicates'] == 1
    result = subprocess.run(command+['-Execute','-BackupRoot',str(backup)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert old.read_text(encoding='utf-8') == 'latest snapshot'
    assert (year/'2026-10'/'2026-10-26.md').read_text(encoding='utf-8') == 'today'
    assert not latest.exists() and not unique.exists()
    assert (backup/'files'/'2026-09'/'2026-09-01.md').read_text(encoding='utf-8') == 'older snapshot'
    assert unknown.read_text(encoding='utf-8') == 'leave me'
    assert json.loads((backup/'result.json').read_text(encoding='utf-8-sig'))['Status'] == 'completed'


@pytest.mark.skipif(os.name != 'nt', reason='Windows file safety checks')
@pytest.mark.parametrize('change', ['source', 'plan'])
def test_organizer_rejects_changed_source_or_tampered_plan_before_mutations(tmp_path, change):
    year = tmp_path/'2026'
    year.mkdir()
    source = year/'2026-10-26.md'
    source.write_text('original', encoding='utf-8')
    plan = tmp_path/'plan.json'
    backup = tmp_path/'backup'
    command = ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(SCRIPT),
               '-Root',str(year),'-PlanPath',str(plan)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    if change == 'source':
        source.write_text('changed after preview', encoding='utf-8')
    else:
        data = json.loads(plan.read_text(encoding='utf-8-sig'))
        data['Groups'][0]['Keeper']['Destination'] = str(year/'2026-10'/'2026-10-25.md')
        plan.write_text(json.dumps(data), encoding='utf-8')
    result = subprocess.run(command+['-Execute','-BackupRoot',str(backup)], capture_output=True)
    assert result.returncode != 0
    assert source.exists()
    assert not backup.exists()
