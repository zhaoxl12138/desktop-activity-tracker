from daylens.services.rule_learning_policy import choose_learning_scope


def test_game_process_can_be_promoted_but_multipurpose_app_stays_title_scoped():
    assert choose_learning_scope("Hades2.exe", "gaming", source="ai") == "process"
    assert choose_learning_scope("wps.exe", "reading", source="ai") == "title"
    assert choose_learning_scope("winword.exe", "office", source="ai") == "title"


def test_shared_browser_never_becomes_process_rule():
    assert choose_learning_scope("chrome.exe", "reading", source="manual",
                                 requested_scope="process") == "title"


def test_explicit_manual_process_scope_is_allowed_for_desktop_app():
    assert choose_learning_scope("custom.exe", "coding", source="manual",
                                 requested_scope="process") == "process"

