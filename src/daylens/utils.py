"""Shared utility functions used across the package."""

WORK_CATEGORY_KEYS = {"ai_tools", "coding", "reading", "creative", "work"}
ENTERTAINMENT_CATEGORY_KEYS = {"video", "gaming", "entertainment"}
SOCIAL_CATEGORY_KEYS = {"social"}
BROWSER_CATEGORY_KEYS = {"browser_general", "browser_other"}
TOOLS_CATEGORY_KEYS = {"tools", "system_tools"}
HIDDEN_RULE_CATEGORY_KEYS = {"idle", "hangup"}


def fmt_seconds(total_seconds):
    """Format seconds into Chinese-readable duration string."""
    total_seconds = total_seconds or 0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    if hours > 0:
        if minutes == 0:
            return f"{hours}时"
        return f"{hours}时{minutes}分"
    if minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


# ── Default config as Python dict ──────────────────────────────────
# Category order: ai_tools, coding, reading, video, creative, social,
# tools, browser_general, other

_DEFAULT_CATEGORIES = {
    "ai_tools": {
        "display_name": "AI工具",
        "active_rule": "interactive_required",
        "process_names": ["chrome.exe", "claude.exe", "msedge.exe", "Doubao.exe"],
        "title_keywords": [
            "ChatGPT", "Claude", "DeepSeek", "Gemini", "Kimi",
            "通义千问", "文心一言", "豆包", "Copilot", "Grok",
            "Perplexity", "Poe",
        ],
    },
    "coding": {
        "display_name": "编程开发",
        "active_rule": "interactive_required",
        "process_names": [
            "Code.exe", "Cursor.exe", "clion64.exe", "Trae CN.exe",
            "codex.exe", "WindowsTerminal.exe", "cmd.exe", "powershell.exe",
            "MobaXterm1_CHS1.exe", "UV4.exe", "notepad++.exe",
            "Docker Desktop.exe", "com.docker.admin.exe",
        ],
        "title_keywords": [
            "VS Code", "Cursor", "Claude Code", "Codex",
            "Visual Studio", "GitHub", "GitLab", "CLion", "Trae",
        ],
    },
    "reading": {
        "display_name": "阅读学习",
        "active_rule": "interactive_required",
        "process_names": [
            "Obsidian.exe", "wps.exe", "wpp.exe", "wpspdf.exe",
            "AcroRd32.exe", "Acrobat.exe", "chrome.exe", "msedge.exe",
        ],
        "title_keywords": [
            "Obsidian", "PDF", "阅读", "文档", "Notion",
            "飞书文档", "语雀", "WPS",
        ],
    },
    "video": {
        "display_name": "娱乐休闲",
        "active_rule": "passive_allowed",
        "process_names": [
            "QyClient.exe", "QyPlayer.exe", "QQLive.exe", "QQMusic.exe",
            "PotPlayerMini64.exe", "PotPlayer.exe", "vlc.exe",
            "chrome.exe", "msedge.exe",
        ],
        "title_keywords": [
            "YouTube", "B站", "bilibili", "腾讯视频", "爱奇艺",
            "Netflix", "抖音", "西瓜视频", "斗鱼", "虎牙", "Twitch",
        ],
    },
    "creative": {
        "display_name": "创作工具",
        "active_rule": "interactive_required",
        "process_names": ["JianyingPro.exe"],
        "title_keywords": [],
    },
    "social": {
        "display_name": "社交通讯",
        "active_rule": "passive_allowed",
        "process_names": [
            "weixin.exe", "WeChat.exe", "WeChatAppEx.exe",
            "WXWork.exe", "QQ.exe", "QClaw.exe",
            "Telegram.exe", "WeMail.exe",
        ],
        "title_keywords": [],
    },
    "tools": {
        "display_name": "系统工具",
        "active_rule": "interactive_required",
        "process_names": [
            "DayLens.exe",
            "ToDesk.exe", "GameViewer.exe", "msrdc.exe",
            "红海Pro兼容版.exe",
            "Everything.exe", "BaiduNetdisk.exe", "localsend_app.exe",
            "WizTree64.exe", "DiskInfo64.exe", "7zFM.exe",
            "Snipaste.exe", "Resilio Sync.exe", "clash-verge.exe",
        ],
        "title_keywords": [],
    },
    "browser_general": {
        "display_name": "浏览器",
        "active_rule": "interactive_required",
        "process_names": [
            "chrome.exe", "msedge.exe", "iexplore.exe",
            "firefox.exe", "360ChromeX.exe",
        ],
        "title_keywords": [],
    },
    "other": {
        "display_name": "其他",
        "active_rule": "interactive_required",
        "process_names": [],
        "title_keywords": [],
    },
}

_CATEGORY_ORDER = [
    "ai_tools", "coding", "reading", "video", "creative",
    "social", "tools", "browser_general", "other",
]

# Track which fields comment each category header
_CATEGORY_COMMENTS = {
    "ai_tools": "AI 工具",
    "coding": "编程开发",
    "reading": "阅读学习",
    "video": "娱乐休闲",
    "creative": "创作工具",
    "social": "社交通讯",
    "tools": "系统工具",
    "browser_general": "浏览器",
    "other": "兜底",
}


def normalize_category_bucket_key(category_key: str, category_name: str = "") -> str:
    """Map fine-grained categories into UI-facing buckets."""
    key = (category_key or "").strip()
    name = (category_name or "").strip()
    if key in WORK_CATEGORY_KEYS or name in {"学习/工作", "工作学习", "办公"}:
        return "work"
    if key in ENTERTAINMENT_CATEGORY_KEYS or name in {"视频娱乐", "视频与游戏", "娱乐休闲"}:
        return "entertainment"
    if key in SOCIAL_CATEGORY_KEYS or name == "社交通讯":
        return "social"
    if key in BROWSER_CATEGORY_KEYS or name in {"浏览器其他", "浏览器兜底", "浏览器"}:
        return "browser_general"
    if key in TOOLS_CATEGORY_KEYS or name == "系统工具":
        return "tools"
    return key or "other"


def normalize_category_display_name(category_key: str, category_name: str = "") -> str:
    """Return the unified UI label for category displays."""
    bucket = normalize_category_bucket_key(category_key, category_name)
    if bucket == "work":
        return "工作学习"
    if bucket == "entertainment":
        return "娱乐休闲"
    if bucket == "social":
        return "社交通讯"
    if bucket == "browser_general":
        return "浏览器"
    if bucket == "tools":
        return "系统工具"
    if category_name in {"浏览器其他", "浏览器兜底"}:
        return "浏览器"
    if category_name in {"视频娱乐", "视频与游戏"}:
        return "娱乐休闲"
    return category_name or "其他"


def normalize_rule_category_display_name(category_key: str, category_name: str = "") -> str:
    """Return rule-list labels without broad work-category merging."""
    key = (category_key or "").strip()
    name = (category_name or "").strip()
    if key in BROWSER_CATEGORY_KEYS or name in {"浏览器其他", "浏览器兜底"}:
        return "浏览器"
    if key in ENTERTAINMENT_CATEGORY_KEYS or name in {"视频娱乐", "视频与游戏"}:
        return "娱乐休闲"
    return name or normalize_category_display_name(key, name)


def should_hide_rule_category(category_key: str, category_name: str = "") -> bool:
    key = (category_key or "").strip()
    name = (category_name or "").strip()
    return key in HIDDEN_RULE_CATEGORY_KEYS or name == "挂机"


def generate_default_config(path):
    """Write default config.yaml, auto-enriched with apps found on this machine."""
    import os
    import yaml

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Attempt app scan (non-fatal if it fails)
    try:
        from .app_scanner import scan_installed_apps, classify_scanned_apps
        scanned = scan_installed_apps()
        classified = classify_scanned_apps(scanned)
    except Exception:
        classified = {}

    # Build categories dict preserving order
    categories = {}
    for key in _CATEGORY_ORDER:
        cat = dict(_DEFAULT_CATEGORIES[key])
        default_procs = cat.pop("process_names")
        title_kws = cat.pop("title_keywords")

        # Merge: default procs (always kept) + scanned procs.
        # Dedup by lowercase, prefer default casing.
        merged = {}
        for p in default_procs:
            merged[p.lower()] = p
        for pname in classified.get(key, set()):
            merged.setdefault(pname, pname)

        cat["match"] = {
            "process_names": sorted(merged.values(), key=str.lower),
            "title_keywords": title_kws,
        }
        categories[key] = cat

    config = {
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 5,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
        },
        "sample_interval_seconds": 5,
        "idle_threshold_seconds": 60,
        "db_path": "data/usage.db",
        "obsidian_output_path": "",
        "categories": categories,
    }

    # Write with header comment
    with open(path, "w", encoding="utf-8") as f:
        f.write("# DayLens 配置文件\n\n")
        f.write("# ── 记录器配置 ──\n")
        f.write(yaml.safe_dump(
            {k: config[k] for k in ["tracker"]},
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        ))
        f.write("\n# ── 基础配置 ──\n")
        f.write(yaml.safe_dump(
            {k: config[k] for k in ["sample_interval_seconds", "idle_threshold_seconds",
                                      "db_path", "obsidian_output_path"]},
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        ))
        f.write("\n# ── 分类规则 ──\n")
        # Write categories with section comments
        category_yaml = yaml.safe_dump(
            {"categories": categories},
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )
        # Inject category section comments
        for key in _CATEGORY_ORDER:
            comment = _CATEGORY_COMMENTS.get(key, "")
            # Replace "  {key}:" with a comment line before it
            marker = f"  {key}:"
            replacement = f"  # ── {comment} ──\n  {key}:"
            category_yaml = category_yaml.replace(marker, replacement)

        f.write(category_yaml)

    return path


# ── Persistent user config (survives PyInstaller rebuilds) ──────────

def load_user_config() -> dict:
    """Load user_config.yaml overrides from data dir. Returns empty dict on failure."""
    import os
    import yaml
    from . import get_data_dir
    user_path = os.path.join(get_data_dir(), "user_config.yaml")
    if not os.path.exists(user_path):
        return {}
    try:
        with open(user_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_user_config(overrides: dict, remove_keys: set[str] | None = None) -> None:
    """Merge overrides into user_config.yaml in the data directory."""
    import os
    import yaml
    from . import get_data_dir
    user_path = os.path.join(get_data_dir(), "user_config.yaml")
    existing = {}
    if os.path.exists(user_path):
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            pass
    for key in remove_keys or set():
        existing.pop(key, None)
    existing.update(overrides)
    os.makedirs(os.path.dirname(user_path), exist_ok=True)
    with open(user_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
