# 数图预约 — 密钥验证 + 预约日志 + 后台管理 服务端

Flask + MySQL + Vue3 后端，单端口同源部署，接口：

- `POST /check_key` — 客户端授权密钥验证（兼容老接口，新增 `user_id` 封禁检查）
- `POST /log_booking` — 客户端上报预约日志
- `GET /health` — 就绪检查（包含数据库连接检测）
- `/api/*` — 后台管理接口（JWT 鉴权）
- `/` — 托管 Vue3 后台管理页面（SPA）

## 目录结构

```text
server/
├── app.py            # Flask 入口 + 全部路由 + SPA 托管
├── config.py         # 读取环境变量，拼数据库连接串
├── db.py             # SQLAlchemy Core 建表 + 全部数据访问函数
├── auth.py           # 密码哈希 + JWT 签发/校验 + login_required 装饰器
├── requirements.txt
├── .env              # 部署侧填写（不提交 git）
└── frontend/         # Vue3 后台管理前端
    ├── src/          # 页面源码
    └── dist/         # npm run build 产物，由 Flask 托管
```

## 功能

后台管理页面（登录后）提供：总览统计、密钥管理（实时修改，立即生效）、日志查看（分页 + 学号/日期筛选）、封禁管理（按学号封禁/解封/编辑，支持到期时间）。

## 部署（Ubuntu/Debian 云服务器）

### 1. 准备 MySQL

```bash
mysql -u root -p <<'SQL'
CREATE DATABASE library_seat DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'library_app'@'localhost' IDENTIFIED BY '改个强密码';
GRANT ALL PRIVILEGES ON library_seat.* TO 'library_app'@'localhost';
FLUSH PRIVILEGES;
SQL
```

### 2. 安装 Python 依赖

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写（或写入 systemd 的 `Environment=`）：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=library_app
DB_PASSWORD=改个强密码
DB_NAME=library_seat
JWT_SECRET=一段足够长的随机字符串
# 以下仅首次启动播种用，之后以数据库为准
LICENSE_KEY=旧key原样
ADMIN_USERNAME=admin
ADMIN_PASSWORD=管理员的强密码
MIN_CLIENT_VERSION=6.0
```

> 首次启动时：`init_db()` 自动建表，并把 `LICENSE_KEY` 写入 `app_config` 表；若 `admins` 表为空且设置了 `ADMIN_USERNAME/PASSWORD`，则创建首个管理员账号。之后改密钥在后台页面操作即可，无需再动环境变量。数据库不可用时服务会快速启动失败，避免出现进程存活但接口不可用的假健康状态。

已有部署升级时，先备份数据库并依次执行：

```bash
mysql -u library_app -p library_seat < server/migrations/001_booking_temporal_types.sql
```

新安装由 `init_db()` 自动创建完整表结构，不需要手动执行迁移。

### 4. 构建前端

```bash
cd server/frontend
npm install
npm run build     # 产物输出到 frontend/dist，Flask 直接托管
```

### 5. 启动

```bash
# 本地/开发（在项目根目录）
python -m server.app

# 生产（gunicorn + systemd，在项目根目录）
gunicorn -w 2 -b 127.0.0.1:5000 server.wsgi:app
```

systemd 示例 `/etc/systemd/system/license.service`：

```ini
[Unit]
Description=Library Seat Booking Server
After=network.target

[Service]
WorkingDirectory=/opt/library-booking
EnvironmentFile=/opt/library-booking/server/.env
ExecStart=/opt/library-booking/venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 server.wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now license
```

### 6. 防火墙

当前客户端允许直接连接 `http://154.8.220.29:5000`。仍建议后续使用 Nginx/Caddy
反向代理并配置 HTTPS；升级后公网仅需放行 `443`。

## 后台使用

浏览器打开 `http://服务器IP:5000/` → 用管理员账号登录 → 左侧菜单进入各页面。

## 客户端配套改动

客户端在提交预约前调用 `/check_ban` 查询当前学号是否被封禁，封禁则拒绝预约。
服务端地址通过环境变量统一配置：

```ini
LIBRARY_CONTROL_SERVER=http://154.8.220.29:5000
```

改完重新打包 exe。

## 安全提示

- `.env` 含数据库密码与 JWT 密钥，绝不提交 git（已在 `.gitignore`）。
- `JWT_SECRET` 必须设强随机值，否则 token 可被伪造。
- `/check_key`、`/log_booking`、`/check_ban` 仍为兼容接口，公网需要限流；整个站点必须启用 HTTPS。
- 封禁在客户端提交预约前检查（用户确认的模型），属尽力而为：封禁服务器故障或学号缺失时放行，不影响正常预约。
