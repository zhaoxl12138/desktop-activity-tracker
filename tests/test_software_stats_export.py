from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from daylens import database
from daylens.services import software_stats_service


def test_csv_export_uses_the_selected_target_path(tmp_path):
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    target = tmp_path / "exports" / "my-usage.csv"

    result = software_stats_service.export_software_csv(str(db_path), str(target))

    assert result == str(target)
    assert target.is_file()


def test_markdown_export_uses_the_selected_target_path(tmp_path):
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    target = tmp_path / "exports" / "my-report.md"

    result = software_stats_service.export_software_markdown(str(db_path), str(target))

    assert result == str(target)
    assert target.is_file()


def _fake_export(content: bytes):
    def export_func(_db_path, _date_str, temp_dir):
        generated = Path(temp_dir) / "generated.csv"
        generated.write_bytes(content)
        return str(generated)

    return export_func


@pytest.mark.parametrize("failure_stage", ["copy", "fsync", "replace"])
def test_selected_target_write_failure_preserves_previous_file(
    tmp_path,
    monkeypatch,
    failure_stage,
):
    target = tmp_path / "exports" / "my-usage.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous export")

    if failure_stage == "copy":
        def fail_copy(source, destination):
            destination.write(b"partial")
            raise OSError("copy failed")

        monkeypatch.setattr(software_stats_service.shutil, "copyfileobj", fail_copy)
    elif failure_stage == "fsync":
        monkeypatch.setattr(
            software_stats_service.os,
            "fsync",
            lambda _fd: (_ for _ in ()).throw(OSError("fsync failed")),
        )
    else:
        real_replace = os.replace

        def fail_target_replace(source, destination):
            if os.path.abspath(destination) == os.path.abspath(target):
                raise OSError("replace failed")
            return real_replace(source, destination)

        monkeypatch.setattr(
            software_stats_service.os,
            "replace",
            fail_target_replace,
        )

    with pytest.raises(OSError, match=f"{failure_stage} failed"):
        software_stats_service._export_to_target(
            _fake_export(b"new export"),
            "unused.db",
            str(target),
        )

    assert target.read_bytes() == b"previous export"
    assert list(target.parent.glob(".my-usage.csv.*.tmp")) == []


def test_concurrent_selected_target_exports_are_complete(tmp_path):
    target = tmp_path / "exports" / "shared.csv"
    barrier = threading.Barrier(2)
    contents = {
        "first": b"first," * 20_000,
        "second": b"second," * 20_000,
    }

    def export_func(db_path, _date_str, temp_dir):
        generated = Path(temp_dir) / "generated.csv"
        generated.write_bytes(contents[db_path])
        barrier.wait(timeout=5)
        return str(generated)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda db_path: software_stats_service._export_to_target(
                    export_func,
                    db_path,
                    str(target),
                ),
                ("first", "second"),
            )
        )

    assert results == [str(target), str(target)]
    assert target.read_bytes() in contents.values()
    assert list(target.parent.glob(".shared.csv.*.tmp")) == []
