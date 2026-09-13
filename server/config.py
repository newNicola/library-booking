"""集中读取环境变量，拼出数据库连接串与各项密钥。

支持从 server/.env 读取（python-dotenv，可选安装）。所有敏感配置一律走环境变量，
绝不硬编码进代码。
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# -- 数据库 --
DB_HOST = _env("DB_HOST", "127.0.0.1")
DB_PORT = _env("DB_PORT", "3306")
DB_USER = _env("DB_USER", "root")
DB_PASSWORD = _env("DB_PASSWORD", "")
DB_NAME = _env("DB_NAME", "library_seat")

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# -- JWT（后台管理登录态）--
JWT_SECRET = _env("JWT_SECRET", "")
JWT_EXPIRE_HOURS = int(_env("JWT_EXPIRE_HOURS", "24") or 24)

# -- 密钥播种（首次启动写入 app_config，之后以库为准）--
LICENSE_KEY = _env("LICENSE_KEY", "")

# -- 管理员播种（admins 表为空时用）--
ADMIN_USERNAME = _env("ADMIN_USERNAME", "")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "")

# -- 旧版 /logs 简单页面查看密钥（可选）--
LOG_VIEW_KEY = _env("LOG_VIEW_KEY", "")
