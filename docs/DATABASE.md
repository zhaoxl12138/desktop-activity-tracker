# 数据库设计

## 概述

使用 SQLite 数据库，WAL 模式，本地存储于 `data/usage.db`。

## activity_logs 表

核心采样记录表，每条记录对应一次窗口采样。

```sql
CREATE TABLE IF NOT EXISTS activity_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,  -- '2026-06-01 14:30:05'
    date            TEXT    NOT NULL,  -- '2026-06-01' (便于按日查询)
    process_name    TEXT    NOT NULL,  -- 'Code.exe'
    exe_path        TEXT,              -- 可执行文件完整路径
    window_title    TEXT    NOT NULL,  -- 窗口标题
    category_key    TEXT    NOT NULL,  -- 'coding', 'ai_tools', 'video', ...
    category_name   TEXT    NOT NULL,  -- '编程开发', 'AI工具', '视频娱乐', ...
    active_rule     TEXT    NOT NULL,  -- 'interactive_required' | 'passive_allowed'
    is_user_active  INTEGER NOT NULL,  -- 0/1 用户是否在操作
    is_effective    INTEGER NOT NULL,  -- 0/1 是否计入有效时间
    idle_seconds    REAL    NOT NULL,  -- 当前空闲秒数
    duration_seconds INTEGER NOT NULL  -- 采样间隔（如 5 秒）
);

CREATE INDEX idx_activity_logs_date ON activity_logs(date);
CREATE INDEX idx_activity_logs_category ON activity_logs(date, category_key);
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | TEXT | 采样时间戳，精确到秒 |
| `date` | TEXT | 日期，冗余字段用于加速按日查询 |
| `process_name` | TEXT | 进程名，如 `chrome.exe` |
| `exe_path` | TEXT | 可执行文件完整路径 |
| `window_title` | TEXT | 窗口标题文本 |
| `category_key` | TEXT | 分类标识符 |
| `category_name` | TEXT | 分类中文名 |
| `active_rule` | TEXT | 计时规则类型 |
| `is_user_active` | INTEGER | 是否有键鼠操作 |
| `is_effective` | INTEGER | 是否计入有效时长 |
| `idle_seconds` | REAL | GetLastInputInfo 返回的空闲秒数 |
| `duration_seconds` | INTEGER | 本条记录代表的时间跨度 |

## 常用查询

### 今日各分类有效时长

```sql
SELECT category_key, category_name,
       SUM(duration_seconds) as total_seconds,
       SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds
FROM activity_logs
WHERE date = '2026-06-01'
GROUP BY category_key
ORDER BY effective_seconds DESC;
```

### 今日 TOP 软件

```sql
SELECT process_name, window_title,
       COUNT(*) * 5 as duration_seconds
FROM activity_logs
WHERE date = '2026-06-01' AND is_effective = 1
GROUP BY process_name
ORDER BY duration_seconds DESC
LIMIT 10;
```

### 多日趋势

```sql
SELECT date, category_key,
       SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds
FROM activity_logs
WHERE date BETWEEN '2026-05-25' AND '2026-06-01'
GROUP BY date, category_key
ORDER BY date;
```

## 数据管理

### 数据库位置

- 默认：`data/usage.db`
- 可在 `config/config.yaml` 中通过 `db_path` 配置

### 数据清理

- GUI 设置页提供一键清理 30 天前记录
- 手动：`sqlite3 data/usage.db "DELETE FROM activity_logs WHERE date < '2026-05-01'"`

### 备份

- GUI 设置页提供备份按钮
- 手动：复制 `data/usage.db` 到其他位置

### 数据量估算

- 每条记录约 200 bytes
- 5 秒采样 → 每天约 17280 条 → 约 3.5 MB/天
- 建议定期清理 30 天前的记录
