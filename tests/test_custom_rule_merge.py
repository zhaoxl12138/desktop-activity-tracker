from desktop_activity_tracker import database


def _base_config():
    return {
        "categories": {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": ["QyClient.exe"],
                    "title_keywords": ["YouTube", "bilibili"],
                },
            }
        }
    }


def test_empty_custom_title_keywords_inherit_builtins(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    database.save_custom_rules(
        str(db_path),
        {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "process_names": ["QyClient.exe"],
                "title_keywords": [],
                "title_keywords_mode": "inherit",
            }
        },
    )
    config = _base_config()

    database.merge_custom_rules(config, str(db_path))

    assert config["categories"]["video"]["match"]["title_keywords"] == [
        "YouTube",
        "bilibili",
    ]


def test_nonempty_custom_title_keywords_override_builtins(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    database.save_custom_rules(
        str(db_path),
        {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "process_names": ["QyClient.exe"],
                "title_keywords": ["自定义视频站"],
            }
        },
    )
    config = _base_config()

    database.merge_custom_rules(config, str(db_path))

    assert config["categories"]["video"]["match"]["title_keywords"] == [
        "自定义视频站",
    ]
