from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_known_mojibake_tokens_in_core_sources():
    checked = [
        ROOT / "src" / "daylens" / "main.py",
        ROOT / "src" / "daylens" / "runtime.py",
        ROOT / "src" / "daylens" / "services" / "command_handlers.py",
        ROOT / "src" / "daylens" / "exporter.py",
        ROOT / "src" / "daylens" / "timeline.py",
        ROOT / "src" / "daylens" / "services" / "settings_service.py",
        ROOT / "src" / "daylens" / "gui" / "pages" / "today_overview.py",
        ROOT / "src" / "daylens" / "repositories" / "stats_repository.py",
    ]
    bad_tokens = [chr(0x7ecc) + chr(0x6d2a) + chr(0x68fd), chr(0xfffd)]

    for path in checked:
        text = path.read_text(encoding="utf-8")
        for token in bad_tokens:
            assert token not in text, f"{path} still contains mojibake token: {token!r}"


def test_runtime_and_cli_prompts_are_human_readable_chinese():
    runtime_text = (ROOT / "src" / "daylens" / "runtime.py").read_text(encoding="utf-8")
    assert "配置文件不存在，正在自动生成默认配置" in runtime_text

    handler_text = (ROOT / "src" / "daylens" / "services" / "command_handlers.py").read_text(encoding="utf-8")
    expected_snippets = [
        "配置:",
        "数据库:",
        "采样间隔:",
        "空闲阈值:",
        "按 Ctrl+C 停止...",
        "正在停止...",
        "数据库已安全关闭。",
        "数据库不存在，请先运行",
        "已导出 CSV:",
        "已导出 Markdown 日报:",
        "已导出周报:",
        "已导出月报:",
        "已同步到 Obsidian:",
    ]
    for snippet in expected_snippets:
        assert snippet in handler_text, f"missing readable CLI prompt: {snippet}"

    bootstrap_text = (ROOT / "src" / "daylens" / "services" / "gui_bootstrap.py").read_text(encoding="utf-8")
    assert "首次运行，已自动分类" in bootstrap_text
    assert "程序已在运行中，请查看系统托盘图标。" in bootstrap_text


def test_report_and_timeline_labels_are_human_readable_chinese():
    exporter_text = (ROOT / "src" / "daylens" / "exporter.py").read_text(encoding="utf-8")
    for snippet in (
        "个人数字行为日报",
        "总览",
        "活跃时间：",
        "挂机/空闲时间：",
        "娱乐时间：",
        "效率评分",
        "分类统计",
        "软件排行",
        "会话时间线",
    ):
        assert snippet in exporter_text

    timeline_text = (ROOT / "src" / "daylens" / "timeline.py").read_text(encoding="utf-8")
    for snippet in (
        "离线",
        "办公",
        "娱乐",
        "混合",
        "低，今天专注度较好",
        "严重碎片化，建议减少频繁切换",
        "办公较集中",
        "娱乐时间控制得当",
    ):
        assert snippet in timeline_text
