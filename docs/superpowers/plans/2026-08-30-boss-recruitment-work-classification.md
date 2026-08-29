# BOSS直聘浏览器工作分类实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让浏览器中的 BOSS直聘页面按主动参与时间计入工作学习。

**Architecture:** 复用现有 `office` 分类及浏览器标题匹配，不新增分类和统计接线。使用品牌名与域名两个精确关键词，避免宽泛“招聘”误判。

**Tech Stack:** Python、PyYAML、pytest、PyInstaller。

---

### Task 1: 分类规则与回归测试

**Files:**
- Modify: `config/config.yaml`
- Modify: `tests/test_classifier_integrity.py`

- [ ] **Step 1: 写入失败测试**

```python
@pytest.mark.parametrize("process_name", ["chrome.exe", "360ChromeX.exe"])
def test_production_boss_recruitment_browser_pages_are_office(process_name):
    result = Classifier(str(PRODUCTION_CONFIG)).classify(
        process_name,
        "BOSS直聘 - 招聘求职找工作 - zhipin.com",
    )
    assert result["category_key"] == "office"
    assert result["active_rule"] == "interactive_required"


def test_generic_recruitment_article_is_not_forced_into_office():
    result = Classifier(str(PRODUCTION_CONFIG)).classify(
        "chrome.exe",
        "招聘行业观察 - 普通资讯页面 - Google Chrome",
    )
    assert result["category_key"] != "office"
```

- [ ] **Step 2: 验证测试按预期失败**

Run: `python -m pytest -q tests/test_classifier_integrity.py -k boss_recruitment`

Expected: BOSS直聘正例当前落入 `browser_general`，测试失败。

- [ ] **Step 3: 添加最小生产规则**

在 `config/config.yaml` 的 `office.match.title_keywords` 中加入：

```yaml
- BOSS直聘
- zhipin.com
```

- [ ] **Step 4: 验证分类测试**

Run: `python -m pytest -q tests/test_classifier_integrity.py`

Expected: 全部通过。

- [ ] **Step 5: 提交规则变更**

```powershell
git add config/config.yaml tests/test_classifier_integrity.py
git commit -m "feat: count BOSS recruitment pages as work"
```

### Task 2: 发布验证

**Files:**
- Build: `release/DayLens.exe`

- [ ] **Step 1: 完整验证**

Run:

```powershell
python -m pytest -q
python -m compileall -q src tests tools
python -m pip check
git diff --check
```

Expected: 全部命令退出码为 0。

- [ ] **Step 2: 构建并启动发布版**

Run: `python tools/build_release.py`

Expected: Qt smoke 成功，`release/DayLens.exe` 被更新。

- [ ] **Step 3: 验证唯一运行路径**

启动发布版，确认仅一个 DayLens 进程、规范数据库仍为 `data/usage.db`，持久日志没有新的 ERROR/CRITICAL。

- [ ] **Step 4: 推送**

Run: `git push origin main`

Expected: `main` 推送成功。
