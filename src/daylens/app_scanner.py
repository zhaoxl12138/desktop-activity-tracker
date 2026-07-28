"""First-run app scanner: discover installed apps from Start Menu + Registry,
match against a built-in knowledge base, and use heuristic classification
for apps not in the knowledge base."""

import os
import re


# ── .lnk shortcut resolver via WScript.Shell COM ───────────────────

_WSH_SHELL = None


def _get_wsh_shell():
    """Lazy-init WScript.Shell COM object."""
    global _WSH_SHELL
    if _WSH_SHELL is None:
        from win32com.client import Dispatch
        _WSH_SHELL = Dispatch("WScript.Shell")
    return _WSH_SHELL


def _resolve_lnk_target(lnk_path: str, shell=None) -> str | None:
    """Extract the target executable path from a Windows .lnk shortcut."""
    try:
        if shell is None:
            shell = _get_wsh_shell()
        shortcut = shell.CreateShortcut(lnk_path)
        target = shortcut.TargetPath
        if target and os.path.isfile(target):
            return target
    except Exception:
        pass
    return None


# ── Name filters ───────────────────────────────────────────────────

_SKIP_PREFIXES = (
    "unins", "unwise", "uninst",
)

_SKIP_CONTAINS = (
    "update", "setup", "install", "uninst", "redist", "prereq",
    "dpinst", "sgtool",
)


def _is_valid_exe_name(name: str) -> bool:
    name_lower = name.lower()
    if not name_lower.endswith(".exe"):
        return False
    base = os.path.basename(name_lower)
    if base.startswith(_SKIP_PREFIXES) or any(s in base for s in _SKIP_CONTAINS):
        return False
    return True


def _extract_exe_from_path(raw: str) -> str | None:
    """Extract the first executable from a registry icon/command value."""
    if not raw:
        return None
    value = os.path.expandvars(str(raw).strip())
    quoted = re.match(r'^\s*"([^"]+?\.exe)"', value, re.IGNORECASE)
    if quoted:
        path = quoted.group(1)
    else:
        unquoted = re.match(r"^\s*(.+?\.exe)(?=\s|,|$)", value, re.IGNORECASE)
        if not unquoted:
            return None
        path = unquoted.group(1).strip()
    if not _is_valid_exe_name(path):
        return None
    return os.path.basename(path).lower()


# ── Scan sources ────────────────────────────────────────────────────

def _scan_start_menu() -> dict[str, str | None]:
    """Scan Start Menu .lnk shortcuts. Returns {exe_name: install_dir}."""
    apps: dict[str, str | None] = {}

    start_menu_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]

    try:
        shell = _get_wsh_shell()
    except Exception:
        shell = None

    for base in start_menu_dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            # Limit depth: only go 3 levels deep from Programs folder
            depth = root[len(base):].count(os.sep)
            if depth > 3:
                _dirs.clear()
                continue
            for fname in files:
                if not fname.lower().endswith(".lnk"):
                    continue
                lnk_path = os.path.join(root, fname)
                target = _resolve_lnk_target(lnk_path, shell)
                if target and _is_valid_exe_name(target):
                    name = os.path.basename(target).lower()
                    install_dir = os.path.dirname(target)
                    if name not in apps:
                        apps[name] = install_dir
    return apps


def _scan_registry_uninstall() -> dict[str, str | None]:
    """Scan Windows registry uninstall entries.
    Returns {exe_name: install_location}.
    """
    import winreg

    apps: dict[str, str | None] = {}
    uninstall_roots = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, key_path in uninstall_roots:
        try:
            with winreg.OpenKey(hive, key_path) as root_key:
                subkey_count = winreg.QueryInfoKey(root_key)[0]
                for i in range(subkey_count):
                    try:
                        subkey_name = winreg.EnumKey(root_key, i)
                        with winreg.OpenKey(root_key, subkey_name) as sk:
                            exe_name = None
                            install_location = None

                            # Try to find the main executable name
                            for val_name in ("DisplayIcon", "UninstallString",
                                             "QuietUninstallString"):
                                try:
                                    raw, _ = winreg.QueryValueEx(sk, val_name)
                                    exe_name = _extract_exe_from_path(raw)
                                    if exe_name:
                                        break
                                except OSError:
                                    pass

                            if not exe_name:
                                continue

                            # Try to get InstallLocation for heuristic classification
                            try:
                                loc, _ = winreg.QueryValueEx(sk, "InstallLocation")
                                if loc and os.path.isdir(loc.strip().strip('"')):
                                    install_location = loc.strip().strip('"')
                            except OSError:
                                pass

                            if exe_name not in apps:
                                apps[exe_name] = install_location
                    except OSError:
                        pass
        except OSError:
            pass

    return apps


def scan_installed_apps() -> dict[str, str | None]:
    """Discover installed applications from Start Menu and Registry.

    Returns {process_name_lowercase: install_dir_or_None}.
    """
    apps: dict[str, str | None] = {}

    try:
        for name, path in _scan_start_menu().items():
            apps[name] = path  # Start Menu path is more specific
    except Exception:
        pass

    try:
        for name, path in _scan_registry_uninstall().items():
            if name not in apps:
                apps[name] = path
    except Exception:
        pass

    return apps


# ── Built-in knowledge base: process_name (lowercase) → category_key ─

KNOWN_APPS: dict[str, str] = {
    # ── AI 工具 ──
    "doubao.exe": "ai_tools",
    "chatgpt.exe": "ai_tools",
    "chatbox.exe": "ai_tools",

    # ── 编程开发 ──
    "code.exe": "coding",
    "cursor.exe": "coding",
    "codex.exe": "coding",
    "sourceinsight4.exe": "coding",
    "clion64.exe": "coding",
    "clion.exe": "coding",
    "pycharm64.exe": "coding",
    "pycharm.exe": "coding",
    "idea64.exe": "coding",
    "idea.exe": "coding",
    "webstorm64.exe": "coding",
    "webstorm.exe": "coding",
    "goland64.exe": "coding",
    "goland.exe": "coding",
    "rider64.exe": "coding",
    "rider.exe": "coding",
    "phpstorm64.exe": "coding",
    "phpstorm.exe": "coding",
    "datagrip64.exe": "coding",
    "datagrip.exe": "coding",
    "devenv.exe": "coding",
    "msbuild.exe": "coding",
    "trae cn.exe": "coding",
    "trae.exe": "coding",
    "windsurf.exe": "coding",
    "zed.exe": "coding",
    "sublime_text.exe": "coding",
    "subl.exe": "coding",
    "atom.exe": "coding",
    "notepad++.exe": "coding",
    "notepad2.exe": "coding",
    "notepad3.exe": "coding",
    "vim.exe": "coding",
    "gvim.exe": "coding",
    "nvim.exe": "coding",
    "neovide.exe": "coding",
    "emacs.exe": "coding",
    "windowsterminal.exe": "coding",
    "wt.exe": "coding",
    "cmd.exe": "coding",
    "powershell.exe": "coding",
    "pwsh.exe": "coding",
    "conemu64.exe": "coding",
    "conemu.exe": "coding",
    "alacritty.exe": "coding",
    "wezterm.exe": "coding",
    "tabby.exe": "coding",
    "warp.exe": "coding",
    "hyper.exe": "coding",
    "mintty.exe": "coding",
    "git-bash.exe": "coding",
    "mobaxterm1_chs1.exe": "coding",
    "mobaxterm.exe": "coding",
    "putty.exe": "coding",
    "kitty.exe": "coding",
    "securecrt.exe": "coding",
    "xshell.exe": "coding",
    "wsl.exe": "coding",
    "git.exe": "coding",
    "gitkraken.exe": "coding",
    "sourcetree.exe": "coding",
    "fork.exe": "coding",
    "tortoisegitproc.exe": "coding",
    "github desktop.exe": "coding",
    "make.exe": "coding",
    "cmake.exe": "coding",
    "cmake-gui.exe": "coding",
    "ninja.exe": "coding",
    "msys2.exe": "coding",
    "uv4.exe": "coding",
    "keil_uvision.exe": "coding",
    "iar embedded workbench.exe": "coding",
    "eclipse.exe": "coding",
    "android studio.exe": "coding",
    "studio64.exe": "coding",
    "docker desktop.exe": "coding",
    "com.docker.admin.exe": "coding",
    "rancher desktop.exe": "coding",
    "dbeaver.exe": "coding",
    "heidisql.exe": "coding",
    "mysqlworkbench.exe": "coding",
    "pgadmin4.exe": "coding",
    "mongodb compass.exe": "coding",
    "redisinsight.exe": "coding",
    "another redis desktop manager.exe": "coding",
    "postman.exe": "coding",
    "insomnia.exe": "coding",
    "bruno.exe": "coding",
    "mremoteng.exe": "coding",
    "wireshark.exe": "coding",
    "fiddler.exe": "coding",
    "fiddler everywhere.exe": "coding",
    "charles.exe": "coding",
    "proxyman.exe": "coding",
    "vncviewer.exe": "tools",
    "virtualbox.exe": "coding",
    "vmware.exe": "coding",
    "vmplayer.exe": "coding",

    # ── 阅读学习 ──
    "obsidian.exe": "reading",
    "logseq.exe": "reading",
    "notion.exe": "reading",
    "typora.exe": "reading",
    "marktext.exe": "reading",
    "zotero.exe": "reading",
    "calibre.exe": "reading",
    "sumatrapdf.exe": "reading",
    "adobe acrobat.exe": "reading",
    "acrord32.exe": "reading",
    "acrobat.exe": "reading",
    "foxit pdf reader.exe": "reading",
    "foxitphantom.exe": "reading",
    "wps.exe": "office",
    "wpp.exe": "office",
    "et.exe": "office",
    "wpspdf.exe": "office",
    "microsoftedge.exe": "browser_general",
    "winword.exe": "office",
    "powerpnt.exe": "office",
    "excel.exe": "office",
    "kindle.exe": "reading",
    "微信读书.exe": "reading",
    "weread.exe": "reading",
    "bookxnote.exe": "reading",
    "bookxnotepro.exe": "reading",
    "xodo.exe": "reading",
    "drawboard pdf.exe": "reading",
    "liquidtext.exe": "reading",
    "margin note.exe": "reading",
    "bear.exe": "reading",
    "craft.exe": "reading",
    "onenote.exe": "office",
    "evernote.exe": "reading",
    "joplin.exe": "reading",

    # ── 娱乐休闲 ──
    "qyclient.exe": "video",
    "qyplayer.exe": "video",
    "qqlive.exe": "video",
    "qqmusic.exe": "video",
    "potplayermini64.exe": "video",
    "potplayer.exe": "video",
    "vlc.exe": "video",
    "mpv.exe": "video",
    "mpc-hc64.exe": "video",
    "mpc-hc.exe": "video",
    "mpc-be64.exe": "video",
    "mpc-be.exe": "video",
    "kmplayer.exe": "video",
    "gump.exe": "video",
    "splayer.exe": "video",
    "iina.exe": "video",
    "cloudmusic.exe": "video",
    "netease cloud music.exe": "video",
    "spotify.exe": "video",
    "foobar2000.exe": "video",
    "aimp.exe": "video",
    "musicbee.exe": "video",
    "tidal.exe": "video",
    "kugou.exe": "video",
    "kwmusic.exe": "video",
    "xiguaplayer.exe": "video",
    "mgv.exe": "video",
    "youku.exe": "video",
    "youkuclient.exe": "video",
    "duonao.exe": "video",
    "bilibili.exe": "video",
    "bililive.exe": "video",

    # ── 创作工具 ──
    "jianyingpro.exe": "creative",
    "capcut.exe": "creative",
    "photoshop.exe": "creative",
    "illustrator.exe": "creative",
    "indesign.exe": "creative",
    "afterfx.exe": "creative",
    "premiere pro.exe": "creative",
    "lightroom.exe": "creative",
    "adobe xd.exe": "creative",
    "figma.exe": "creative",
    "sketch.exe": "creative",
    "lunacy.exe": "creative",
    "gimp.exe": "creative",
    "inkscape.exe": "creative",
    "krita.exe": "creative",
    "blender.exe": "creative",
    "maya.exe": "creative",
    "3dsmax.exe": "creative",
    "cinema 4d.exe": "creative",
    "davinci resolve.exe": "creative",
    "resolve.exe": "creative",
    "obs64.exe": "creative",
    "obs32.exe": "creative",
    "streamlabs obs.exe": "creative",
    "bandicam.exe": "creative",
    "camtasia.exe": "creative",
    "xmind.exe": "creative",
    "mindmanager.exe": "creative",
    "drawio.exe": "creative",
    "edrawmax.exe": "creative",
    "canva.exe": "creative",
    "pixso.exe": "creative",
    "mastergo.exe": "creative",

    # ── 社交通讯 ──
    "weixin.exe": "social",
    "wechat.exe": "social",
    "wechatappex.exe": "social",
    "wxwork.exe": "social",
    "qq.exe": "social",
    "qclaw.exe": "social",
    "telegram.exe": "social",
    "wemail.exe": "social",
    "dingtalk.exe": "social",
    "feishu.exe": "social",
    "lark.exe": "social",
    "zoom.exe": "social",
    "teams.exe": "social",
    "slack.exe": "social",
    "discord.exe": "social",
    "skype.exe": "social",
    "signal.exe": "social",
    "whatsapp.exe": "social",
    "line.exe": "social",
    "thunderbird.exe": "social",
    "outlook.exe": "office",
    "foxmail.exe": "social",
    "mailmaster.exe": "social",
    "spark desktop.exe": "social",
    "tim.exe": "social",
    "aliwangwang.exe": "social",
    "yy.exe": "social",

    # ── 系统工具 ──
    "todesk.exe": "tools",
    "gameviewer.exe": "tools",
    "msrdc.exe": "tools",
    "mstsc.exe": "tools",
    "红海pro兼容版.exe": "tools",
    "everything.exe": "tools",
    "listary.exe": "tools",
    "flow launcher.exe": "tools",
    "utools.exe": "tools",
    "wox.exe": "tools",
    "powertoys.exe": "tools",
    "powertoys.settings.exe": "tools",
    "powertoys.run.exe": "tools",
    "baidunetdisk.exe": "tools",
    "localsend_app.exe": "tools",
    "wiztree64.exe": "tools",
    "diskinfo64.exe": "tools",
    "7zfm.exe": "tools",
    "bandizip.exe": "tools",
    "winrar.exe": "tools",
    "peazip.exe": "tools",
    "snipaste.exe": "tools",
    "greenshot.exe": "tools",
    "sharex.exe": "tools",
    "lightshot.exe": "tools",
    "resilio sync.exe": "tools",
    "syncthing.exe": "tools",
    "clash-verge.exe": "tools",
    "clash verge.exe": "tools",
    "v2rayn.exe": "tools",
    "hiddify.exe": "tools",
    "nekobox.exe": "tools",
    "nekoray.exe": "tools",
    "sing-box.exe": "tools",
    "crystaldiskinfo.exe": "tools",
    "crystaldiskmark.exe": "tools",
    "hwinfo64.exe": "tools",
    "hwinfo32.exe": "tools",
    "cpu-z.exe": "tools",
    "gpu-z.exe": "tools",
    "speccy64.exe": "tools",
    "speccy.exe": "tools",
    "ccleaner64.exe": "tools",
    "ccleaner.exe": "tools",
    "windirstat.exe": "tools",
    "spacesniffer.exe": "tools",
    "treesize.exe": "tools",
    "treesizefree.exe": "tools",
    "rufus.exe": "tools",
    "ventoy2disk.exe": "tools",
    "balenaetcher.exe": "tools",
    "win32diskimager.exe": "tools",
    "diskgenius.exe": "tools",
    "aomei partition assistant.exe": "tools",
    "minitool partition wizard.exe": "tools",
    "ultraiso.exe": "tools",
    "daemontools.exe": "tools",
    "virtual clonedrive.exe": "tools",
    "powertoys.colorpickerui.exe": "tools",
    "powertoys.powerrename.exe": "tools",
    "powertoys.awake.exe": "tools",
    "quicklook.exe": "tools",
    "seer.exe": "tools",
    "regedit.exe": "tools",
    "taskmgr.exe": "tools",
    "mmc.exe": "tools",
    "control.exe": "tools",
    "charmap.exe": "tools",
    "cleanmgr.exe": "tools",
    "dfrgui.exe": "tools",
    "msconfig.exe": "tools",
    "magnify.exe": "tools",
    "wmplayer.exe": "video",
    "wordpad.exe": "reading",
    "explorer.exe": "tools",

    # ── 游戏（已合并至娱乐休闲）──
    "steam.exe": "video",
    "wegame.exe": "video",
    "epic games launcher.exe": "video",
    "ubisoft connect.exe": "video",
    "origin.exe": "video",
    "ea app.exe": "video",
    "battle.net.exe": "video",
    "gog galaxy.exe": "video",
    "ubisoftconnect.exe": "video",
    "eadesktop.exe": "video",
    "itch.exe": "video",
    "xbox app.exe": "video",
    "rockstar games launcher.exe": "video",

    # ── 浏览器（通用）──
    "chrome.exe": "browser_general",
    "firefox.exe": "browser_general",
    "iexplore.exe": "browser_general",
    "chromium.exe": "browser_general",
    "brave.exe": "browser_general",
    "vivaldi.exe": "browser_general",
    "opera.exe": "browser_general",
    "arc.exe": "browser_general",
    "zen.exe": "browser_general",
    "thorium.exe": "browser_general",
    "360chromex.exe": "browser_general",
    "360chrome.exe": "browser_general",
    "qqbrowser.exe": "browser_general",
    "sogouexplorer.exe": "browser_general",
    "maxthon.exe": "browser_general",
    "theworld.exe": "browser_general",
    "librewolf.exe": "browser_general",
    "waterfox.exe": "browser_general",
    "pale moon.exe": "browser_general",
    "basilisk.exe": "browser_general",
}


# ── Heuristic classification for apps not in KNOWN_APPS ─────────────

# Keywords found in the install path or exe name → category
_PATH_KEYWORDS: dict[str, list[str]] = {
    "coding": [
        "jetbrains", "visual studio", "vscode", "dev-cpp", "codeblocks",
        "android studio", "eclipse", "xcode", "labview", "matlab",
        "arduino", "platformio", "stm32", "keil", "iar systems",
        "source insight", "understand", "beyond compare",
        "python", "anaconda", "miniconda", "pycharm", "nodejs",
        "mingw", "msys2", "cygwin", "llvm", "cmake", "ninja",
        "openjdk", "jdk", "dotnet", "golang", "rust", "cargo",
        "docker", "rancher", "kubernetes", "podman",
        "git", "github", "gitlab", "bitbucket", "sourcetree",
        "postman", "insomnia", "wireshark", "fiddler",
        "dbeaver", "heidisql", "mysql", "postgresql", "mongodb", "redis",
        "mobaxterm", "putty", "xshell", "securecrt", "terminal", "console",
        "virtualbox", "vmware", "qemu",
        "unity", "unreal engine", "godot", "cocos",
        "cubemx", "mplab", "atmel", "nordic", "espressif", "renesas",
    ],
    "office": [
        "wps office", "microsoft office", "libreoffice", "openoffice",
        "word", "excel", "powerpoint", "onenote", "outlook",
    ],
    "reading": [
        "obsidian", "logseq", "notion", "typora", "zotero", "calibre",
        "pdf", "ebook", "kindle", "read", "document", "note",
        "evernote",
        "知网", "cajviewer", "cnki",
    ],
    "video": [
        "potplayer", "vlc", "mpv", "kmplayer", "gump", "splayer",
        "qqmusic", "kugou", "cloudmusic", "netease", "spotify", "tidal",
        "video", "player", "media", "music", "audio", "stream",
        "bilibili", "youtube", "youku", "iqiyi", "netflix",
        "douyin", "tiktok", "kuaishou", "xigua",
        "steam", "epic games", "ubisoft", "origin", "battle.net",
        "gog", "wegame", "riot games", "blizzard", "miHoYo",
        "hoyoverse", "ea games", "rockstar",
        "game", "gaming",
    ],
    "creative": [
        "adobe", "photoshop", "illustrator", "premiere", "after effect",
        "lightroom", "indesign", "blender", "maya", "cinema 4d",
        "figma", "sketch", "lunacy", "canva", "mastergo", "pixso",
        "coreldraw", "affinity", "clip studio", "sai", "krita",
        "davinci resolve", "capcut", "jianying", "shotcut", "obs studio",
        "xmind", "mindmanager", "edraw", "draw.io", "processon",
        "camtasia", "bandicam", "screen recorder",
        "design", "creative", "edit", "draw", "paint", "render", "animate",
    ],
    "social": [
        "wechat", "weixin", "qq", "telegram", "dingtalk", "feishu", "lark",
        "slack", "discord", "skype", "teams", "zoom", "signal",
        "whatsapp", "line", "messenger", "im", "chat", "talk",
        "thunderbird", "foxmail", "mailmaster", "mail",
    ],
    "tools": [
        "everything", "listary", "wiztree", "spacesniffer", "windirstat",
        "treesize", "diskinfo", "crystaldisk", "hwinfo", "cpu-z", "gpu-z",
        "ccleaner", "speccy", "rufus", "ventoy", "etcher",
        "7-zip", "winrar", "bandizip", "peazip", "winzip",
        "baidunetdisk", "localsend", "syncthing", "resilio",
        "todesk", "anydesk", "teamviewer", "vnc", "mstsc", "rustdesk",
        "snipaste", "greenshot", "sharex", "lightshot",
        "clash", "v2ray", "hiddify", "nekobox", "nekoray", "sing-box",
        "powertoys", "quicklook", "seer",
        "diskgenius", "partition", "ultraiso", "daemon",
        "file manager", "commander", "explorer",
        "tool", "utility", "system", "monitor", "cleaner", "security",
    ],
}

_NAME_KEYWORDS: dict[str, list[str]] = {
    "coding": [
        "studio", "ide", "editor", "terminal", "console", "shell",
        "git", "dev", "build", "compile", "debug", "code",
    ],
    "office": ["word", "excel", "powerpoint", "outlook", "wps"],
    "reading": ["read", "pdf", "ebook", "note", "doc"],
    "video": ["player", "video", "music", "audio", "media", "stream", "play", "game", "steam", "launcher"],
    "creative": ["design", "draw", "paint", "animate", "render", "compose"],
    "social": ["chat", "msg", "talk", "im", "mail", "message"],
    "tools": ["manager", "monitor", "tool", "utility", "clean", "viewer"],
}


def _heuristic_classify(name: str, install_path: str | None) -> str | None:
    """Guess category for an app not found in KNOWN_APPS.

    Uses install path first (more reliable), then executable name.
    Returns category_key or None.
    """
    name_no_ext = name.replace(".exe", "")

    # Build a combined search text from install path + exe name
    search_text = (install_path or "").lower() + " " + name_no_ext.lower()

    best_cat = None
    best_len = 0

    for cat_key, keywords in _PATH_KEYWORDS.items():
        for kw in keywords:
            if kw in search_text:
                if len(kw) > best_len:
                    best_len = len(kw)
                    best_cat = cat_key

    if best_cat:
        return best_cat

    # Fallback: executable name patterns only
    for cat_key, keywords in _NAME_KEYWORDS.items():
        for kw in keywords:
            if kw in name_no_ext.lower():
                if len(kw) > best_len:
                    best_len = len(kw)
                    best_cat = cat_key

    return best_cat


# ── Classification entry point ─────────────────────────────────────

def classify_scanned_apps(apps: dict[str, str | None]) -> dict[str, set[str]]:
    """Classify scanned apps into categories.

    Priority: KNOWN_APPS exact match > heuristic (install path) > heuristic (name).
    Returns {category_key: {process_name, ...}}.
    """
    result: dict[str, set[str]] = {}

    for pname, install_path in apps.items():
        # 1. Exact knowledge base match
        cat = KNOWN_APPS.get(pname.lower())
        # 2. Heuristic fallback
        if cat is None:
            cat = _heuristic_classify(pname, install_path)

        if cat:
            result.setdefault(cat, set()).add(pname)

    return result
