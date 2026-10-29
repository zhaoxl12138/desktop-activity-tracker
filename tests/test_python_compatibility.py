from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_widgets_avoids_python312_only_same_quote_fstring_expression():
    source = (
        ROOT / "src" / "daylens" / "gui" / "widgets" / "dashboard_widgets.py"
    ).read_text(encoding="utf-8")

    assert 'f"<span style=\'color:{COLORS["' not in source
