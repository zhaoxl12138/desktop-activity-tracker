# iPhone 屏幕使用时间

DayLens 可以读取 Daylog 导出的 iPhone 屏幕使用时间。在 Daylog 配好接收端后，将 DayLens 设置里的 Obsidian 输出路径指向该库。手机归档应位于库内的 `时间追踪/手机屏幕使用时间/YYYY/YYYY-MM/YYYY-MM-DD.md`。

## DayLens 本地副本

iPhone 每天 00:00 把昨天的数据发到 Daylog。DayLens 运行时从 00:05 起检查并复制已收到的记录，启动后和每次小时日报刷新时也会补查。点「数据统计 → 手机使用时间 → 刷新」可立即请求同步。

同步沿用设置中的 Obsidian 输出路径来定位 Daylog，并按日期复制 Markdown 到 DayLens 数据库旁的 `iphone-screen-time/YYYY/YYYY-MM/`。榜单始终读取本地副本。Daylog 暂时不可访问时，已复制的日期仍可查看。换电脑时，把这个目录和 DayLens 的数据库一起迁移即可保留历史榜单。
