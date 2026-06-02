"""Shared utility functions used across the package."""


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


DEFAULT_CONFIG_YAML = """\
# DayLens 配置文件

# ── 记录器配置 ──
tracker:
  sample_interval_seconds: 1     # 窗口检测频率（秒）
  flush_interval_seconds: 10     # 强制写库间隔（秒）
  idle_threshold_seconds: 60     # 空闲判定阈值（秒）
  min_session_seconds: 2         # 最短 session，低于此值不写库

# ── 基础配置 ──
sample_interval_seconds: 5
idle_threshold_seconds: 60
db_path: "data/usage.db"
obsidian_output_path: ""

categories:

  # ── AI 工具 ──────────────────────────────────────────
  ai_tools:
    display_name: "AI工具"
    active_rule: "interactive_required"
    match:
      process_names:
        - "chrome.exe"
        - "msedge.exe"
        - "Doubao.exe"             # 豆包桌面版
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
        - "Grok"
        - "Perplexity"
        - "Poe"

  # ── 编程开发 ──────────────────────────────────────────
  coding:
    display_name: "编程开发"
    active_rule: "interactive_required"
    match:
      process_names:
        # 编辑器 / IDE
        - "Code.exe"               # VS Code
        - "Cursor.exe"             # Cursor
        - "clion64.exe"            # CLion
        - "Trae CN.exe"            # Trae (字节跳动 AI IDE)
        # CLI / 终端
        - "codex.exe"              # Codex CLI
        - "WindowsTerminal.exe"
        - "cmd.exe"
        - "powershell.exe"
        - "MobaXterm1_CHS1.exe"    # MobaXterm SSH
        # 嵌入式开发
        - "UV4.exe"                # Keil MDK
        # 编辑器
        - "notepad++.exe"          # Notepad++
        # Docker
        - "Docker Desktop.exe"
        - "com.docker.admin.exe"
      title_keywords:
        - "VS Code"
        - "Cursor"
        - "Claude Code"
        - "Codex"
        - "Visual Studio"
        - "GitHub"
        - "GitLab"
        - "CLion"
        - "Trae"

  # ── 阅读学习 ──────────────────────────────────────────
  reading:
    display_name: "阅读学习"
    active_rule: "interactive_required"
    match:
      process_names:
        # 笔记 / PDF
        - "Obsidian.exe"
        - "wps.exe"                # WPS 文字
        - "wpp.exe"                # WPS 演示
        - "wpspdf.exe"             # WPS PDF
        - "AcroRd32.exe"
        - "Acrobat.exe"
        # 浏览器阅读
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
        - "WPS"

  # ── 视频娱乐 ──────────────────────────────────────────
  video:
    display_name: "视频娱乐"
    active_rule: "passive_allowed"
    match:
      process_names:
        # 视频客户端
        - "QyClient.exe"           # 爱奇艺
        - "QyPlayer.exe"           # 爱奇艺播放器
        - "QQLive.exe"             # 腾讯视频
        - "QQMusic.exe"            # QQ音乐
        # 本地播放器
        - "PotPlayerMini64.exe"
        - "PotPlayer.exe"
        - "vlc.exe"
        # 浏览器（看视频）
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
        - "斗鱼"
        - "虎牙"
        - "Twitch"

  # ── 创作工具 ──────────────────────────────────────────
  creative:
    display_name: "创作工具"
    active_rule: "interactive_required"
    match:
      process_names:
        - "JianyingPro.exe"        # 剪映专业版

  # ── 社交通讯 ──────────────────────────────────────────
  social:
    display_name: "社交通讯"
    active_rule: "passive_allowed"
    match:
      process_names:
        - "weixin.exe"
        - "WeChat.exe"
        - "WeChatAppEx.exe"        # 微信进程
        - "WXWork.exe"             # 企业微信
        - "QQ.exe"
        - "QClaw.exe"              # QQ claw
        - "Telegram.exe"
        - "WeMail.exe"             # 企业微信邮箱

  # ── 系统工具 ──────────────────────────────────────────
  tools:
    display_name: "系统工具"
    active_rule: "interactive_required"
    match:
      process_names:
        # 远程控制
        - "ToDesk.exe"
        - "GameViewer.exe"         # UU远程
        - "msrdc.exe"              # 微软远程桌面
        - "红海Pro兼容版.exe"       # 红海远程
        # 文件工具
        - "Everything.exe"         # 文件搜索
        - "BaiduNetdisk.exe"       # 百度网盘
        - "localsend_app.exe"      # LocalSend
        - "WizTree64.exe"          # 磁盘分析
        - "DiskInfo64.exe"         # CrystalDiskInfo
        - "7zFM.exe"               # 7-Zip
        # 截图 / 录屏
        - "Snipaste.exe"
        # 同步
        - "Resilio Sync.exe"
        # 网络
        - "clash-verge.exe"

  # ── 游戏 ──────────────────────────────────────────────
  gaming:
    display_name: "游戏"
    active_rule: "passive_allowed"
    match:
      process_names:
        - "Steam.exe"
        - "WeGame.exe"

  # ── 浏览器兜底 ────────────────────────────────────────
  browser_general:
    display_name: "浏览器其他"
    active_rule: "interactive_required"
    match:
      process_names:
        - "chrome.exe"
        - "msedge.exe"
        - "iexplore.exe"
        - "firefox.exe"
        - "360ChromeX.exe"

  # ── 兜底 ──────────────────────────────────────────────
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
