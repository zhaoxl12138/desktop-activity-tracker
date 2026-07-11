from __future__ import annotations

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
