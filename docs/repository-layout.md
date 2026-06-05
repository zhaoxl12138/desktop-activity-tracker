# DayLens 仓库目录约定

## 代码与配置

- `src/`：应用源码
- `tests/`：自动化测试
- `config/`：默认配置模板
- `assets/`：图标和静态资源
- `tools/`：辅助脚本

## 运行期数据

- `data/`：本地数据库与运行时数据
- `reports/`：导出的日报、周报、月报

这两个目录都属于运行产物，不属于源码本体。

## 构建与发布产物

- `build/`：PyInstaller 构建中间产物
- `build_temp/`：本地临时构建目录
- `dist/`：打包输出目录
- `release/`：当前本地发布版整理目录
- `DayLens/`：历史 onedir 或手工解压产物

这些目录都属于构建或发布产物，默认不应参与源码版本管理。

清理这些目录时，统一使用 `tools/cleanup_runtime_artifacts.py`。
默认是 `dry-run`，只会列出计划清理的 `build/`、`build_temp/`、`dist/`、`DayLens/`。
只有显式加 `--apply` 才会真正删除；`release/` 只有配合 `--include-release` 才会纳入清理。

## 当前约定

- 日常开发只关注 `src/`、`tests/`、`config/`、`assets/`
- 本地运行数据统一落到 `data/`、`reports/`
- 打包验证优先看一个明确的发布目录，不要混用 `dist/`、`release/`、`DayLens/`
- 提交前确认没有把运行数据和构建产物带进版本库
- 发布构建统一通过 `tools/build_release.py` 准备 `release/`
- 构建目录清理统一通过 `tools/cleanup_runtime_artifacts.py`
