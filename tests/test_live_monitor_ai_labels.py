from daylens.gui.pages.live_monitor import classification_label, review_row_values


def test_pending_ai_title_is_not_presented_as_other():
    assert classification_label('其他', {
        'source': 'AI待识别',
        'suggested_category': '',
    }) == '待识别'


def test_uncertain_ai_title_shows_suggestion_without_applying_it():
    assert classification_label('浏览器', {
        'source': 'AI待确认',
        'suggested_category': 'reading',
    }) == '待确认 · 建议工作学习'


def test_applied_ai_title_keeps_real_category_name_and_source():
    assert classification_label('影音娱乐', {
        'source': 'AI',
        'suggested_category': 'video',
    }) == '影音娱乐 · AI'


def test_rule_title_keeps_plain_category_name():
    assert classification_label('办公', {'source': '规则'}) == '办公'


def test_history_label_uses_each_samples_classification_detail():
    assert classification_label('浏览器', {
        'source': 'AI待确认', 'suggested_category': 'reading',
    }) == '待确认 · 建议工作学习'


def test_review_row_exposes_reason_occurrences_and_active_time():
    values = review_row_values({
        'app': 'chrome.exe', 'title': '学习中心', 'suggested_category': 'reading',
        'certainty': 'medium', 'reason': '课程学习', 'occurrences': 3,
        'active_seconds': 95,
    })
    assert values == ('chrome.exe', '学习中心', '工作学习 · 中', '课程学习', '3次 · 1分35秒')
