# DayLens Hidden Bug Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复已复现的分类、首页统计、节奏窗口、日报聚合与运行日志缺陷，并保持唯一数据库和现有历史会话不被代码静默改写。

**Architecture:** 在现有边界内做局部修复：分类器提供统一关键词语义，首页展示模型保证秒数守恒，节奏模型统一滚动窗口与事实数据口径，导出器先聚合展示大类，GUI 启动层安装轮转日志。所有改动通过生产配置和真实服务函数的回归测试驱动。

**Tech Stack:** Python 3.12、PySide6、SQLite、PyYAML、pytest、PyInstaller。

---

### Task 1: 修复关键词边界与 OBS 归类

**Files:**
- Modify: `src/daylens/classifier.py:87-93`
- Modify: `config/config.yaml`
- Modify: `src/daylens/repositories/settings_repository.py`（若自定义规则合并需要迁移 OBS 所属分类）
- Test: `tests/test_classifier_integrity.py`
- Test: `tests/test_rules_discovery_persistence.py`

- [ ] **Step 1: 写入失败回归测试**

```python
def test_ascii_keywords_do_not_match_inside_larger_words(production_config):
    classifier = Classifier(str(production_config))
    assert classifier.classify(
        "chrome.exe", "World Military Ranking - YouTube - Google Chrome"
    )["category_key"] == "video"
    assert classifier.classify(
        "chrome.exe", "American History Documentary - YouTube - Google Chrome"
    )["category_key"] == "video"


def test_obs_is_creative_not_passive_video(production_config):
    result = Classifier(str(production_config)).classify("obs64.exe", "OBS Studio")
    assert result["category_key"] == "creative"
    assert result["active_rule"] == "interactive_required"
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run: `python -m pytest tests/test_classifier_integrity.py -q`

Expected: Ranking/American 当前得到 `reading`，OBS 当前得到 `video`。

- [ ] **Step 3: 实现最小关键词匹配与规则归属修复**

```python
_ASCII_WORD_KEYWORD = re.compile(r"^[a-z0-9]+$")


def _keyword_matches(title_folded: str, keyword: str) -> bool:
    if not _ASCII_WORD_KEYWORD.fullmatch(keyword):
        return keyword in title_folded
    return re.search(
        rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
        title_folded,
    ) is not None
```

让 `_match_title` 调用 `_keyword_matches`。从 `video` 中移除 `obs64.exe` 和 `OBS`，保留在 `creative`；对已存在的自定义规则只迁移这一明确冲突，不更改其他用户规则。

- [ ] **Step 4: 验证定向测试**

Run: `python -m pytest tests/test_classifier_integrity.py tests/test_rules_discovery_persistence.py -q`

Expected: PASS。

- [ ] **Step 5: 提交分类修复**

```bash
git add src/daylens/classifier.py config/config.yaml src/daylens/repositories/settings_repository.py tests/test_classifier_integrity.py tests/test_rules_discovery_persistence.py
git commit -m "fix: prevent classifier keyword collisions"
```

### Task 2: 修复时间分布漏项并保持展示守恒

**Files:**
- Modify: `src/daylens/services/dashboard_service.py:1174-1228`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py:2540-2590`
- Test: `tests/test_dashboard_service.py:510-570`
- Test: `tests/test_homepage_redesign.py`

- [ ] **Step 1: 写入失败回归测试**

```python
def test_distribution_sections_preserve_all_effective_seconds():
    stats = {"by_category": [
        {"category_key": "coding", "effective_seconds": 600},
        {"category_key": "browser_general", "effective_seconds": 300},
        {"category_key": "tools", "effective_seconds": 120},
        {"category_key": "other", "effective_seconds": 180},
    ]}
    sections = build_distribution_sections(stats, effective_seconds=1200)
    assert sum(row["seconds"] for row in sections) == 1200
    assert sections[-1]["label"] == "浏览器等"
    assert sections[-1]["seconds"] == 600
```

- [ ] **Step 2: 运行测试并确认当前只得到900秒**

Run: `python -m pytest tests/test_dashboard_service.py -k distribution_sections -q`

Expected: FAIL，`other` 和未领先残余分类被漏掉。

- [ ] **Step 3: 扩展残余聚合模型**

给 `category_seconds` 增加 `other`；第四行以最长残余分类决定 key、颜色和主标签，但秒数为全部残余分类合计。多个残余分类非零时在标签后加“等”。UI 继续按模型提供的 key 和 label 渲染，不增加第五行。

- [ ] **Step 4: 验证服务与首页测试**

Run: `python -m pytest tests/test_dashboard_service.py tests/test_homepage_redesign.py -q`

Expected: PASS。

- [ ] **Step 5: 提交分布修复**

```bash
git add src/daylens/services/dashboard_service.py src/daylens/gui/widgets/dashboard_widgets.py tests/test_dashboard_service.py tests/test_homepage_redesign.py
git commit -m "fix: preserve residual dashboard time"
```

### Task 3: 让近7天包含今天并统一今日节奏事实口径

**Files:**
- Modify: `src/daylens/services/dashboard_service.py:538-610`
- Modify: `src/daylens/services/dashboard_service.py:717-750`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_dashboard_widgets.py`

- [ ] **Step 1: 写入失败回归测试**

```python
def test_seven_day_rhythm_includes_captured_today():
    model = _build_seven_day_rhythm(
        datetime(2026, 8, 29, 12, 0, 0), daily_rows, comparison_allowed=False
    )
    assert model["date_range"] == ["2026-08-23", "2026-08-29"]
    assert model["chart"]["labels"] == [
        "8/23", "8/24", "8/25", "8/26", "8/27", "8/28", "8/29"
    ]


def test_today_rhythm_keeps_same_day_sessions_across_classification_versions():
    model = build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 29, 20, 0, 0),
        sessions=[old_version_work_session, current_version_work_session],
        daily_rows=[],
        query_failed=False,
    )
    assert max(value for value in model["today"]["chart"]["current"] if value is not None) == 808
    assert model["today"]["metrics"][0]["value"] == "15:09"
```

- [ ] **Step 2: 运行测试并确认日期与累计值失败**

Run: `python -m pytest tests/test_dashboard_service.py -k "seven_day or classification_versions" -q`

Expected: 近7天结束于8/28；今日节奏只保留最新分类版本。

- [ ] **Step 3: 修改滚动窗口和同日过滤**

近7天以 `captured_now.date()` 为结束日，前7日比较窗口相应前移。今日事实曲线保留全部 `attention-v1` 且计时守恒的工作会话；分类断点仍让 `comparison.comparable=False` 并显示“口径已变化”，但不删除事实数据。

- [ ] **Step 4: 验证节奏测试**

Run: `python -m pytest tests/test_dashboard_service.py tests/test_dashboard_widgets.py -q`

Expected: PASS。

- [ ] **Step 5: 提交节奏修复**

```bash
git add src/daylens/services/dashboard_service.py tests/test_dashboard_service.py tests/test_dashboard_widgets.py
git commit -m "fix: align rolling rhythm windows"
```

### Task 4: 合并日报展示分类并纠正最长软件字段

**Files:**
- Modify: `src/daylens/exporter.py:233-323`
- Create: `tests/test_exporter.py`
- Test: `tests/test_trusted_report_fields.py`

- [ ] **Step 1: 写入失败回归测试**

```python
def test_markdown_report_merges_work_categories_and_names_top_software(tmp_path):
    path = export_markdown(str(db_path), "2026-08-29", str(tmp_path))
    text = Path(path).read_text(encoding="utf-8-sig")
    assert text.count("| 工作学习 |") == 1
    assert "- 最长使用软件：ChatGPT.exe" in text
    assert "- 最长使用软件：窗口里的长文章标题" not in text
```

- [ ] **Step 2: 运行测试并确认重复行和标题误用**

Run: `python -m pytest tests/test_exporter.py tests/test_trusted_report_fields.py -q`

Expected: FAIL。

- [ ] **Step 3: 添加日报展示聚合帮助函数**

按 `work/video/social/browser/other` 聚合当前与昨日秒数，并在聚合键集合中选择 Top 应用和 Top 内容。总览的最长软件只使用 `process_name`，必要时调用既有显示名称解析器，不读取 `window_title`。

- [ ] **Step 4: 验证报表测试并重新生成当日日报样本**

Run: `python -m pytest tests/test_exporter.py tests/test_trusted_report_fields.py tests/test_reports_service.py -q`

Expected: PASS；生成文本中“工作学习”只有一行。

- [ ] **Step 5: 提交报表修复**

```bash
git add src/daylens/exporter.py tests/test_exporter.py tests/test_trusted_report_fields.py tests/test_reports_service.py
git commit -m "fix: aggregate daily report categories"
```

### Task 5: 增加发布版持久化运行日志

**Files:**
- Create: `src/daylens/services/logging_service.py`
- Modify: `src/daylens/services/gui_bootstrap.py:78-129`
- Modify: `src/daylens/gui/worker.py:358-448`
- Create: `tests/test_logging_service.py`
- Test: `tests/test_main_architecture.py`

- [ ] **Step 1: 写入失败日志测试**

```python
def test_configure_app_logging_writes_uncaught_exception(tmp_path):
    log_path = configure_app_logging(str(tmp_path / "usage.db"))
    try:
        raise RuntimeError("sentinel crash")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "sentinel crash" in Path(log_path).read_text(encoding="utf-8")


def test_logging_setup_failure_does_not_abort_gui(monkeypatch):
    monkeypatch.setattr(logging_service, "RotatingFileHandler", failing_handler)
    assert configure_app_logging("Z:/unavailable/usage.db") is None
```

- [ ] **Step 2: 运行测试并确认模块尚不存在**

Run: `python -m pytest tests/test_logging_service.py -q`

Expected: FAIL，无法导入 `logging_service`。

- [ ] **Step 3: 实现轮转日志与异常钩子**

使用 `RotatingFileHandler(maxBytes=2_000_000, backupCount=3, encoding="utf-8")`，安装 `sys.excepthook`，在 PySide6 导入后安装 Qt 消息处理器。启动日志写入版本、PID、数据库路径；工作线程 fatal/degraded 事件写入同一 logger。初始化失败只返回 `None`。

- [ ] **Step 4: 验证日志与启动测试**

Run: `python -m pytest tests/test_logging_service.py tests/test_main_architecture.py tests/test_recording_worker.py -q`

Expected: PASS。

- [ ] **Step 5: 提交日志修复**

```bash
git add src/daylens/services/logging_service.py src/daylens/services/gui_bootstrap.py src/daylens/gui/worker.py tests/test_logging_service.py tests/test_main_architecture.py tests/test_recording_worker.py
git commit -m "fix: persist GUI runtime failures"
```

### Task 6: 历史数据精确修正与最终验证

**Files:**
- Modify data only after backup: `data/usage.db`
- Regenerate: `data/reports/daily/2026/2026-08/2026-08-22.md` through `2026-08-24.md`
- Regenerate affected weekly/monthly reports through existing report service
- Build: `release/DayLens.exe`

- [ ] **Step 1: 备份并列出唯一目标行**

创建带时间戳的数据库备份；只选择当前生产分类器会判为 `video`、但库中为工作类的12条8月22日至24日会话。输出 ID、日期、时间和秒数，确认合计4113秒。

- [ ] **Step 2: 执行单事务修正并验证守恒**

将目标行更新为 `category_key='video'`、`category_name='娱乐休闲'`、`active_rule='passive_allowed'` 和当前分类版本；不改时间戳及五个计时字段。事务后运行 `PRAGMA quick_check` 和新版计时守恒查询。

- [ ] **Step 3: 重新生成受影响报表**

通过 `reports_service` 重新生成8月22日至24日日报、包含这些日期的周报及8月月报，检查工作与娱乐总量迁移4113秒。

- [ ] **Step 4: 运行全部验证**

```powershell
python -m pytest -q
python -m compileall -q src tests tools
python -m pip check
git diff --check
```

Expected: 全量测试0失败；compileall、pip check、diff check退出码均为0。

- [ ] **Step 5: 构建并运行发布版验证**

重新构建 `release/DayLens.exe`，运行 Qt smoke，启动唯一发布路径，验证单实例、唯一数据库、日志文件、日报刷新和持续采样；观察至少60秒，无新 Windows Application Error。

- [ ] **Step 6: 提交代码和报表之外的允许变更并推送**

检查 `git status`，不纳入用户未跟踪文件。仅在用户既有 push 授权范围内推送当前分支。
