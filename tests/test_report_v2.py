from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from daylens import database, exporter
from daylens.services.daily_goal_service import GoalStore
from daylens.services.report_sections import START, END


def new_db(tmp_path):
    path = tmp_path / "usage.db"
    database.init_db(str(path)).close()
    return path


def insert(
    path,
    day="2026-10-20",
    seconds=10,
    *,
    category="coding",
    identity="s1",
    title="编辑项目",
    passive=0,
    idle=0,
):
    start = datetime.fromisoformat(day + " 09:00:00")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,normalized_title,
             category_key,category_name,duration_seconds,effective_seconds,
             engaged_seconds,passive_seconds,idle_seconds,metric_version,classification_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity,
                str(start),
                str(start + timedelta(seconds=seconds + passive + idle)),
                day,
                "app.exe",
                title,
                category,
                category,
                seconds + passive + idle,
                seconds + passive,
                seconds,
                passive,
                idle,
                "attention-v1",
                "rules-test",
            ),
        )


@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 61, 3599, 3600])
def test_report_session_seconds_are_never_rounded_up(tmp_path, seconds):
    db = new_db(tmp_path)
    insert(db, seconds=seconds)
    text = Path(
        exporter.export_markdown(str(db), "2026-10-20", str(tmp_path / "out"))
    ).read_text(encoding="utf-8")
    from daylens.services.report_v2_renderer import duration

    line = next(line for line in text.splitlines() if "| 编辑项目 |" in line)
    assert "| " + duration(seconds) + " |" in line
    assert "## 关键发现" in text
    assert "效率评分" not in text
    assert "最专注" not in text


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
@pytest.mark.parametrize("populated", [False, True])
def test_v2_all_reports_have_same_structure_without_ai_or_source_writes(
    tmp_path, kind, populated, monkeypatch
):
    from daylens.services.intelligence_client import DeepSeekProvider

    monkeypatch.setattr(
        DeepSeekProvider,
        "request_json",
        lambda *_a, **_k: pytest.fail("network request"),
    )
    db = new_db(tmp_path)
    if populated:
        insert(db, seconds=4000)
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT * FROM activity_sessions").fetchall()
    args = {
        "daily": (exporter.export_markdown, ("2026-10-20",)),
        "weekly": (exporter.export_weekly_report, (2026, 43)),
        "monthly": (exporter.export_monthly_report, (2026, 10)),
    }
    fn, middle = args[kind]
    target = fn(str(db), *middle, str(tmp_path / "out"))
    text = Path(target).read_text(encoding="utf-8")
    for heading in ["## 关键发现", "## 总览", "## 目标与成果", "## 详细数据"]:
        assert heading in text
    assert all(
        word not in text
        for word in ("效率评分", "最专注", "时间黑洞", "需改进", "行为画像")
    )
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM activity_sessions").fetchall() == before


def test_v2_preserves_existing_ai_and_other_history(tmp_path):
    db = new_db(tmp_path)
    out = tmp_path / "out"
    old = out / "2020.md"
    out.mkdir()
    old.write_bytes(b"untouched historical report")
    path = Path(exporter.export_markdown(str(db), "2026-10-20", str(out)))
    appendix = START + "\n## 智能汇总\nOLD AI\n" + END
    path.write_text(
        path.read_text(encoding="utf-8") + "\n" + appendix, encoding="utf-8"
    )
    exporter.export_markdown(str(db), "2026-10-20", str(out))
    assert appendix in path.read_text(encoding="utf-8")
    assert old.read_bytes() == b"untouched historical report"


def test_v2_context_has_one_mixed_source_and_no_per_day_queries(tmp_path, monkeypatch):
    from daylens.services.report_v2_service import build_context
    from daylens.repositories import stats_repository

    db = new_db(tmp_path)
    insert(db, seconds=61)
    with sqlite3.connect(db) as conn:
        conn.execute("""INSERT INTO activity_logs(timestamp,date,process_name,window_title,
            category_key,category_name,is_effective,duration_seconds)
            VALUES ('2026-10-20 12:00:00','2026-10-20','old.exe','旧记录','reading','阅读学习',1,120)""")
    calls = []
    original = stats_repository._load_mixed_history_rows

    def load(*args):
        calls.append(args[2])
        return original(*args)

    monkeypatch.setattr(stats_repository, "_load_mixed_history_rows", load)
    model = build_context(
        str(db), "daily", ["2026-10-20"], now=datetime(2026, 10, 21, 12)
    )
    assert len(calls) == 1
    assert model["stats"]["totals"]["effective_seconds"] == 181
    assert model["stats"]["totals"]["work_engaged_seconds"] == 61
    assert model["trust"]["level"] == "low"
    assert model["comparison"]["comparable"] is False


def test_v2_goals_and_unsafe_text_are_rendered_without_completion_inference(tmp_path):
    from daylens.services.report_v2_service import build_context
    from daylens.services.report_v2_renderer import render_report

    db = new_db(tmp_path)
    insert(db, seconds=61, title='<img src="https://example.com/x"> | next\nline')
    store = GoalStore(tmp_path / "intelligence")
    store.save_day(
        "2026-10-20",
        [
            {
                "id": "g1",
                "type": "time_commitment",
                "title": "学习 | <script>",
                "target_kind": "category",
                "target_id": "work",
                "target_minutes": 1,
                "confirmed": False,
                "confirmed_at": None,
            }
        ],
        expected_revision=0,
    )
    model = build_context(str(db), "daily", ["2026-10-20"], now=datetime(2026, 10, 21))
    assert model["goals"]["status"] == "ready"
    assert model["goals"]["rows"][0]["actual_seconds"] == 61
    text = render_report(model)
    assert "计划 / 投入 / 已确认成果" in text
    assert "时间目标达到计划时长不等于成果完成" in text
    assert "<img" not in text and "<script>" not in text
    assert "\\|" in text
    assert len(model["actions"]) <= 1


def test_v2_comparison_uses_completed_aligned_dates():
    from daylens.services.report_v2_service import comparison_dates

    current, previous = comparison_dates(
        "weekly", [f"2026-10-{d:02}" for d in range(19, 26)], date(2026, 10, 22)
    )
    assert current == ["2026-10-19", "2026-10-20", "2026-10-21"]
    assert previous == ["2026-10-12", "2026-10-13", "2026-10-14"]
    current, previous = comparison_dates(
        "monthly", [f"2026-03-{d:02}" for d in range(1, 32)], date(2026, 3, 31)
    )
    assert len(current) == len(previous) == 28
    assert previous[-1] == "2026-02-28"


def test_anomalous_session_is_labeled_and_not_promoted_to_finding(tmp_path):
    from daylens.services.report_v2_service import build_context
    from daylens.services.report_v2_renderer import render_report

    db = new_db(tmp_path)
    insert(db, seconds=60)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE activity_sessions SET effective_seconds=600")
    model = build_context(str(db), "daily", ["2026-10-20"], now=datetime(2026, 10, 21))
    assert not any(f["type"] == "category" for f in model["facts"])
    assert "计量异常" in render_report(model)


def test_corrupt_counter_does_not_stop_native_reports(tmp_path):
    db = new_db(tmp_path)
    insert(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE activity_sessions SET effective_seconds='broken'")
    result = exporter.export_markdown(str(db), "2026-10-20", str(tmp_path / "reports"))
    text = Path(result).read_text(encoding="utf-8")
    assert "计量异常" in text and "未知" in text


@pytest.mark.parametrize("bad", ["broken", 123, b"invalid"])
def test_malformed_interval_is_presented_without_crashing_or_rewriting(tmp_path, bad):
    db = new_db(tmp_path)
    insert(db)
    insert(db, identity="other")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE activity_sessions SET start_time=?,end_time=? WHERE session_id=?",
            (bad, bad, "other"),
        )
    result = exporter.export_markdown(str(db), "2026-10-20", str(tmp_path / "reports"))
    assert "计量异常" in Path(result).read_text(encoding="utf-8")
