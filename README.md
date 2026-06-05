# DayLens

> 看清时间花在哪里。

DayLens 是一个本地 Windows 桌面应用，用来记录前台窗口使用情况，分类统计活跃时间、挂机时间、娱乐时间和社交通讯时间，并生成日报、周报、月报。

## 功能

- 自动记录前台窗口和会话切换
- 区分活跃时间与挂机时间
- 统计分类分布、趋势、时间线、Top 软件
- 导出 Markdown / CSV 报告
- 支持同步到 Obsidian

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

## License

MIT
