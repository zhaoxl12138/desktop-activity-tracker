# 2026-10-28 短采样缺口边界验收记录

## 改动

- 记录线程两次采样之间超过 `max(5秒, 3×采样间隔)`、但未达到系统休眠阈值时，以 `sampling_gap` 结束旧会话。
- 旧会话结束时间固定在上一次成功采样时刻；缺口不计入前台、参与、被动或空闲时间。
- 当前窗口在缺口后从新会话继续记录；系统休眠/锁屏的大缺口仍要求重新出现活动证据后恢复。
- 不修改历史数据库、表结构、正常采样间隔和既有 `system_gap` 语义。

## TDD

- 10 秒缺口回归先失败：旧实现没有结束会话，前台范围会跨过未知间隔。
- 最小修改后，10 秒缺口产生 `sampling_gap`，前后会话各只含 1 秒真实采样。
- 2 秒抖动保持同一会话；10 分钟缺口仍为 `system_gap`。
- 记录、边界回滚和测量定向测试：`115 passed in 1.11s`。

## 完整验证

- `python -m pytest -q`：`1334 passed in 43.04s`。
- `python -m compileall -q src`：exit 0。
- `python tests/test_gui_smoke.py`：100%、125%、150% 顺序运行均通过。
- `git diff --check`：exit 0，仅有既有 LF/CRLF 提示。
- `python tools/build_release.py --stage-only`：exit 0，打包 Qt 与 Windows 凭据 smoke 通过。

## 发布确认

- 旧回退版保留为 `release_previous_20261028_before_sampling_gap/`，刚替换下来的分类口径版保留在 `release_previous/`。
- 新版通过维护命令安全退出旧程序后原子替换，只启动一次；最终唯一进程 PID 65044，窗口可见且响应正常。
- 运行心跳更新到 `2026-10-28T10:33:16+08:00`，采样诊断更新到 `2026-10-28T10:33:15`，记录线程已工作。
- 新版 SHA-256：`8F7F1663E005D19BF893E8230F6E33A5CE27D9D7A3D75F5AD075FDD4E8EB701C`；上一版 SHA-256：`C8CB97949790901926E606D41E0661652D3863ACD44ABE39F77A041934E72697`。

