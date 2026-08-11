from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from daylens import database, exporter


REPORT_DATE = "2026-08-10"


def _new_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    return db_path


def _insert_session(
    db_path: Path,
    *,
    session_id: str,
    start: str,
    end: str,
    duration: int,
    effective: int,
    engaged: int,
    passive: int,
    idle: int,
    metric_version: str = "attention-v1",
    classification_version: str = "rules-a",
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO activity_sessions (
                session_id, start_time, end_time, date, process_name,
                window_title, normalized_title, category_key, category_name,
                active_rule, duration_seconds, effective_seconds,
                engaged_seconds, passive_seconds, idle_seconds,
                metric_version, classification_version, switch_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                f"{REPORT_DATE} {start}",
                f"{REPORT_DATE} {end}",
                REPORT_DATE,
                "code.exe",
                "main.py",
                "main.py",
                "coding",
                "编程开发",
                "interactive_required",
                duration,
                effective,
                engaged,
                passive,
                idle,
                metric_version,
                classification_version,
                "test",
            ),
        )


def _insert_legacy_log(db_path: Path, *, duration: int = 60) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO activity_logs (
                timestamp, date, process_name, window_title, category_key,
                category_name, active_rule, is_user_active, is_effective,
                idle_seconds, duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{REPORT_DATE} 10:00:00",
                REPORT_DATE,
                "legacy.exe",
                "Legacy",
                "other",
                "其他",
                "interactive_required",
                1,
                1,
                0,
                duration,
            ),
        )


def _export_markdown(db_path: Path, tmp_path: Path) -> str:
    path = exporter.export_markdown(
        str(db_path),
        REPORT_DATE,
        str(tmp_path / "reports"),
    )
    return Path(path).read_text(encoding="utf-8")


def _export_csv_rows(db_path: Path, tmp_path: Path) -> list[list[str]]:
    path = exporter.export_csv(
        str(db_path),
        REPORT_DATE,
        str(tmp_path / "reports"),
    )
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def test_daily_markdown_appends_high_trust_attention_fields_once(tmp_path: Path):
    db_path = _new_database(tmp_path)
    _insert_session(
        db_path,
        session_id="high",
        start="10:00:00",
        end="10:02:00",
        duration=120,
        effective=90,
        engaged=60,
        passive=30,
        idle=30,
    )

    report = _export_markdown(db_path, tmp_path)

    for old_section in ("## 总览", "- 活跃时间：", "## 分类统计", "## 软件排行"):
        assert old_section in report
    assert report.count("- 参与时间：1分0秒") == 1
    assert report.count("- 被动媒体：30秒") == 1
    assert report.count("- 数据可信度：高") == 1
    assert "- 数据可信度：高（" not in report


@pytest.mark.parametrize(
    ("arrange", "expected_level", "expected_reason"),
    [
        (
            "mixed-classification",
            "中",
            "范围内存在多个分类版本",
        ),
        (
            "legacy-session",
            "低",
            "旧计量口径占比超过20%",
        ),
        (
            "legacy-log",
            "低",
            "旧日志缺少会话粒度",
        ),
        (
            "anomaly",
            "低",
            "计时组成异常率超过0.5%",
        ),
        (
            "empty",
            "低",
            "范围内没有可评估记录",
        ),
    ],
)
def test_daily_markdown_reports_real_attention_trust_scenarios(
    tmp_path: Path,
    arrange: str,
    expected_level: str,
    expected_reason: str,
):
    db_path = _new_database(tmp_path)
    if arrange == "mixed-classification":
        _insert_session(
            db_path,
            session_id="mixed-a",
            start="10:00:00",
            end="10:01:00",
            duration=60,
            effective=60,
            engaged=60,
            passive=0,
            idle=0,
            classification_version="rules-a",
        )
        _insert_session(
            db_path,
            session_id="mixed-b",
            start="10:01:00",
            end="10:02:00",
            duration=60,
            effective=60,
            engaged=60,
            passive=0,
            idle=0,
            classification_version="rules-b",
        )
    elif arrange == "legacy-session":
        _insert_session(
            db_path,
            session_id="legacy",
            start="10:00:00",
            end="10:01:00",
            duration=60,
            effective=60,
            engaged=0,
            passive=0,
            idle=0,
            metric_version="legacy",
            classification_version="legacy",
        )
    elif arrange == "legacy-log":
        _insert_legacy_log(db_path)
    elif arrange == "anomaly":
        _insert_session(
            db_path,
            session_id="anomaly",
            start="10:00:00",
            end="10:01:00",
            duration=60,
            effective=10,
            engaged=10,
            passive=0,
            idle=0,
        )

    report = _export_markdown(db_path, tmp_path)

    assert f"- 数据可信度：{expected_level}（{expected_reason}）" in report
    if arrange in {"legacy-session", "legacy-log", "empty"}:
        assert "- 参与时间：0秒" in report
        assert "- 被动媒体：0秒" in report


def test_daily_csv_keeps_old_columns_and_appends_trusted_values(tmp_path: Path):
    db_path = _new_database(tmp_path)
    _insert_session(
        db_path,
        session_id="csv",
        start="10:00:00",
        end="10:02:00",
        duration=120,
        effective=90,
        engaged=60,
        passive=30,
        idle=30,
    )

    rows = _export_csv_rows(db_path, tmp_path)

    assert rows[0][:4] == ["日期", "总有效时长(秒)", "总空闲时长(秒)", "总采样数"]
    assert rows[0][4:] == [
        "参与时长(秒)",
        "被动媒体时长(秒)",
        "数据可信度",
        "可信度原因",
    ]
    assert rows[1][:4] == [REPORT_DATE, "90", "30", "1"]
    assert rows[1][4:] == ["60", "30", "高", ""]
    assert rows[3] == ["分类统计"]
    assert rows[4][:5] == [
        "分类Key",
        "分类名称",
        "有效时长(秒)",
        "空闲时长(秒)",
        "总时长(秒)",
    ]


def test_daily_csv_preserves_utf8_bom_and_csv_newlines(tmp_path: Path):
    db_path = _new_database(tmp_path)

    path = exporter.export_csv(
        str(db_path),
        REPORT_DATE,
        str(tmp_path / "reports"),
    )
    payload = Path(path).read_bytes()

    assert payload.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in payload


def test_daily_csv_uses_first_real_reason_and_replaces_on_regeneration(tmp_path: Path):
    db_path = _new_database(tmp_path)
    _insert_legacy_log(db_path)

    first_rows = _export_csv_rows(db_path, tmp_path)
    second_rows = _export_csv_rows(db_path, tmp_path)

    assert first_rows[1][4:] == ["0", "0", "低", "旧日志缺少会话粒度"]
    assert second_rows == first_rows
    assert sum(row == first_rows[0] for row in second_rows) == 1


def test_trust_calculation_failure_is_sanitized_for_markdown_and_csv(
    tmp_path: Path,
    monkeypatch,
):
    db_path = _new_database(tmp_path)
    monkeypatch.setattr(
        exporter,
        "assess_range",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("secret internal detail")
        ),
    )

    report = _export_markdown(db_path, tmp_path)
    rows = _export_csv_rows(db_path, tmp_path)

    assert "- 数据可信度：低（可信度计算异常）" in report
    assert rows[1][6:] == ["低", "可信度计算异常"]
    assert "secret internal detail" not in report
    assert all("secret internal detail" not in cell for row in rows for cell in row)
