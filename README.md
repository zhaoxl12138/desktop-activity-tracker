# DayLens

> 看清时间花在哪里。

DayLens 是一个本地 Windows 桌面应用，用来记录前台窗口使用情况，分类统计活跃时间、挂机时间、娱乐时间和社交通讯时间，并生成日报、周报、月报。

## 功能

- 自动记录前台窗口和会话切换
- 区分活跃时间与挂机时间
- 统计分类分布、趋势、时间线、Top 软件
- 导出 Markdown / CSV 报告
- 支持同步到 Obsidian
- 可选的 V1.6 本地任务链：在统计页查看任务候选、会话依据与任务级切换观察，并纠正确认、拆分或移动会话归属；不改动原始计时和分类
- 可选的云端任务命名建议：每批先预览脱敏请求并手动确认发送；离线、无密钥或预算不足时保留本地结果
- V1.7 每日目标：在“今日计划”或“统计 → 目标”设置最多 3 项时间/成果目标；时间目标比较可信主动参与，成果目标只接受用户手动确认
- 周报在原有内容后增加“计划 / 投入 / 已确认成果”，不把目标达时长当成完成成果

任务分析和云端建议在设置中心分别开启，默认均关闭。任务候选与“返回任务”只是可核对的分析，不代表工作成果或认知恢复成本；任务级插入事件也不替代原有“明显中断”指标。人工纠错保存在本地 `data/intelligence/` 的派生文件中，不修改历史会话、日报或分类。

每日目标也保存在同一规范 `intelligence/` 目录的独立派生 JSON。未设置目标不会产生目标判断；没有可信会话时显示“证据不足”，不补成 0。V1.7 不自动读取 Git 仓库或笔记作为成果证据；周报中的“用户确认”仅代表用户手动勾选。

## 运行

### 发布版

解压发布包后，运行 `DayLens.exe`。

### 源码启动

```bash
pip install -r requirements.txt
python -m daylens.main
```

### 构建发布版

```bash
python tools/build_release.py
```

仅构建并验证隔离发布包、不退出或替换当前程序时，使用 `python tools/build_release.py --stage-only`。

构建完成后，以 `release/` 作为唯一发布目录。

### 清理历史构建产物

```bash
python tools/cleanup_runtime_artifacts.py
python tools/cleanup_runtime_artifacts.py --apply
```

默认是 `dry-run`，只列出将清理的 `build/`、`build_temp/`、`dist/`、`DayLens/`。  
如果需要把 `release/` 也一起清掉，再额外加 `--include-release`。

## 仓库目录

- `src/`：源码
- `tests/`：测试
- `config/`：默认配置
- `assets/`：静态资源
- `data/`：本地数据库与运行时数据
- `reports/`：导出的日报、周报、月报
- `release/`：当前发布版目录
- `dist/` / `build/` / `build_temp/` / `DayLens/`：构建或历史产物
- `tools/cleanup_runtime_artifacts.py`：清理历史构建目录

更完整说明见 `docs/repository-layout.md`。

## 开发约定

- 改代码只改 `src/`
- 运行数据只写入 `data/`、`reports/`
- 不提交 `build/`、`dist/`、`release/`、`DayLens/` 等构建产物
- 清理历史构建目录统一使用 `tools/cleanup_runtime_artifacts.py`
- 提交前优先跑自动化测试

## V1.8 本地行为画像与一周实验

设置中心开启“本地行为画像与一周实验”后，进入报告中心的“行为画像”。提供近7、14、30个完整日的可信记录、投入时段、候选任务插入与连续工作片段对照；新生成的日报/周报/月报包含同一分析小节。此能力不调用API，不新增费用，也不会修改既有会话或自动重写历史报告。

用户主动接受实验后，从次日起观察7个完整日，再与接受前7个完整日对照。实验可停止。缺记录、版本混用、异常或基线证据变化时不生成效果结论；记录覆盖不代表全天覆盖，观察差异也不证明因果关系。关闭设置即可停止新分析。实验状态存放在规范 intelligence 目录的 `behavior_experiment_v1.json`，原始数据库无需迁移。

## License

MIT
