"""Shared utility functions used across the package."""


def fmt_seconds(total_seconds):
    """Format seconds into Chinese-readable duration string."""
    total_seconds = total_seconds or 0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


DEFAULT_CONFIG_YAML = """\
# Desktop Activity Tracker 配置文件
sample_interval_seconds: 5
idle_threshold_seconds: 60
db_path: "data/usage.db"
obsidian_output_path: ""

categories:
  ai_tools:
    display_name: "AI工具"
    active_rule: "interactive_required"
    match:
      process_names:
        - "chrome.exe"
        - "msedge.exe"
      title_keywords:
        - "ChatGPT"
        - "Claude"
        - "DeepSeek"
        - "Gemini"
        - "Kimi"
        - "通义千问"
        - "文心一言"
        - "豆包"
        - "Copilot"

  coding:
    display_name: "编程开发"
    active_rule: "interactive_required"
    match:
      process_names:
        - "Code.exe"
        - "Cursor.exe"
        - "WindowsTerminal.exe"
        - "cmd.exe"
        - "powershell.exe"
        - "codex.exe"
      title_keywords:
        - "VS Code"
        - "Cursor"
        - "Claude Code"
        - "Codex"
        - "Visual Studio"
        - "GitHub"

  reading:
    display_name: "阅读学习"
    active_rule: "interactive_required"
    match:
      process_names:
        - "Obsidian.exe"
        - "wps.exe"
        - "AcroRd32.exe"
        - "Acrobat.exe"
        - "chrome.exe"
        - "msedge.exe"
      title_keywords:
        - "Obsidian"
        - "PDF"
        - "阅读"
        - "文档"
        - "Notion"
        - "飞书文档"
        - "语雀"

  video:
    display_name: "视频娱乐"
    active_rule: "passive_allowed"
    match:
      process_names:
        - "PotPlayerMini64.exe"
        - "PotPlayer.exe"
        - "vlc.exe"
        - "QQLive.exe"
        - "chrome.exe"
        - "msedge.exe"
      title_keywords:
        - "YouTube"
        - "B站"
        - "bilibili"
        - "腾讯视频"
        - "爱奇艺"
        - "Netflix"
        - "抖音"
        - "西瓜视频"

  browser_general:
    display_name: "浏览器其他"
    active_rule: "interactive_required"
    match:
      process_names:
        - "chrome.exe"
        - "msedge.exe"
        - "iexplore.exe"
        - "firefox.exe"

  other:
    display_name: "其他"
    active_rule: "interactive_required"
    match:
      process_names: []
      title_keywords: []
"""


def generate_default_config(path):
    """Write default config.yaml to the given path."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_CONFIG_YAML)
