import json

from daylens.services.intelligence_evidence import (
    ReviewQueue,
    load_patterns,
    match_pattern,
    save_pattern,
    set_pattern_enabled,
)


def test_manual_pattern_reuses_similar_title_only_inside_same_app(tmp_path):
    saved = save_pattern(
        tmp_path,
        '360ChromeX.exe',
        '学习中心 - 视频课程 - 自考公共课 - 360极速浏览器X',
        'reading',
    )
    patterns = load_patterns(tmp_path)

    decision = match_pattern(
        patterns,
        '360ChromeX.exe',
        '学习中心 - 视频课程 - 自考专业课 - 360极速浏览器X',
    )

    assert decision['category'] == 'reading'
    assert decision['source'] == '人工模式'
    assert decision['pattern_id'] == saved['id']
    assert match_pattern(patterns, 'chrome.exe', '学习中心 - 视频课程 - 自考专业课') is None
    assert match_pattern(patterns, '360ChromeX.exe', '豆瓣电影排行榜') is None


def test_disabled_pattern_no_longer_matches(tmp_path):
    pattern = save_pattern(tmp_path, 'chrome.exe', '学习中心 - 视频课程', 'reading')
    set_pattern_enabled(tmp_path, pattern['id'], False)

    assert match_pattern(load_patterns(tmp_path), 'chrome.exe', '学习中心 - 视频课程') is None


def test_pattern_file_contains_redacted_example_not_sensitive_values(tmp_path):
    save_pattern(
        tmp_path,
        'chrome.exe',
        '学习中心 视频课程 alice@example.com 13812345678 https://secret/a?token=x',
        'reading',
    )

    raw = (tmp_path / 'title_patterns.json').read_text(encoding='utf-8')
    assert 'alice@example.com' not in raw
    assert '13812345678' not in raw
    assert 'token=x' not in raw


def test_review_queue_is_bounded_aggregated_and_resolvable(tmp_path):
    queue = ReviewQueue(tmp_path, limit=3)
    for index in range(4):
        queue.upsert({
            'id': f'id-{index}', 'app': 'chrome.exe', 'title': f'Title {index}',
            'category': 'reading', 'certainty': 'medium', 'reason': '可能是课程',
            'active_seconds': 30,
        })
    queue.upsert({
        'id': 'id-3', 'app': 'chrome.exe', 'title': 'Title 3',
        'category': 'reading', 'certainty': 'medium', 'reason': '可能是课程',
        'active_seconds': 15,
    })

    rows = queue.items()
    assert [row['id'] for row in rows] == ['id-3', 'id-2', 'id-1']
    assert rows[0]['occurrences'] == 2
    assert rows[0]['active_seconds'] == 45

    queue.ignore('id-3')
    assert [row['id'] for row in queue.items()] == ['id-2', 'id-1']
    stored = json.loads((tmp_path / 'classification_reviews.json').read_text(encoding='utf-8'))
    assert len(stored['items']) == 2
