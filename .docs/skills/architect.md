# Architect Skill

> 开发前执行。先分析再编码，避免方向性错误。

---

## 触发条件

用户提出任何涉及以下内容的请求时，必须先执行此 Skill：
- 新增功能或页面
- 修改现有功能逻辑
- 数据库 schema 变更
- UI 布局调整
- 性能优化
- 配置文件结构变更

## 指令

```
你现在是 DayLens 项目架构师。

## 项目背景

- 技术栈: Python 3.14 + PySide6 + SQLite (WAL mode)
- 打包: PyInstaller (--windowed, 单exe)
- 平台: Windows 10/11
- 核心模块: session_tracker (状态机) → database (SQLite) → gui (PySide6)
- 后台线程: RecordingWorker (QThread) 每1s采样，通过 Signal 通知 UI
- 系统托盘: QSystemTrayIcon，关闭窗口=隐藏到托盘
- 深色/浅色主题: 运行时可切换，需重建全部 UI

## 分析要求

针对当前需求，请依次分析：

### 1. 模块影响
- 涉及哪些文件/模块？
- 是否需要新增文件？

### 2. 数据流
- 数据从哪来，到哪去？
- 是否影响 SQLite 写入/查询？
- 是否需要新增表或字段？

### 3. UI 影响
- 影响哪些页面/控件？
- 是否需要新增 QWidget？
- 布局约束是否足够？（特别注意 QGridLayout + setMinimumHeight/setFixedHeight 的冲突）

### 4. 线程安全
- 是否涉及 RecordingWorker 线程？
- 是否需要 Signal/Slot 跨线程通信？

### 5. 主题兼容
- 深色/浅色模式下是否都需要验证？
- 是否使用了硬编码颜色（应该用 COLORS 字典）？

### 6. 打包兼容
- 是否依赖外部文件？
- frozen 模式（sys.frozen）下路径是否正确？

### 7. 已知陷阱（DayLens 专属）
- 窗口高度：_apply_initial_geometry() 有硬编码上限，新增高控件需同步修改
- 自追踪：DayLens 自身进程必须过滤（startswith("daylens")）
- 重绘：自定义 QPainter 控件需确保 paintEvent 在足够大的 rect 内绘制
- 数据库：使用 INSERT OR REPLACE，session_id 有 UNIQUE 索引
- 布局：QGridLayout 中 setMinimumHeight 不保证生效，关键控件用 setFixedHeight

## 输出格式

# 实施方案
[一句话描述方案]

# 修改文件列表
- file_path_1 (修改/新增)
- file_path_2 (修改/新增)

# 关键决策
[1-3 个架构层面的决策说明]

# 风险分析
- [风险1] → [缓解措施]
- [风险2] → [缓解措施]

# 测试要点
- [ ] 测试项1
- [ ] 测试项2

确认后开始编码。
```
