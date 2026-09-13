"""数据库访问层：建表、密钥/管理员播种，以及全部数据读写函数。

使用 SQLAlchemy Core（text() + 参数绑定），仅 engine + 连接池，不引入 ORM 模型。
所有 SQL 收敛在本文件，未来换存储实现只改这里。
"""

import datetime
import logging

from sqlalchemy import create_engine, text

import config

log = logging.getLogger(__name__)

engine = create_engine(
    config.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)


def init_db() -> None:
    """建表 + 播种密钥与默认管理员。服务启动时调用一次。"""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS admins (
          id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          username      VARCHAR(64)  NOT NULL UNIQUE,
          password_hash VARCHAR(255) NOT NULL,
          created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_login_at DATETIME     NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS app_config (
          config_key   VARCHAR(64)  PRIMARY KEY,
          config_value VARCHAR(512) NOT NULL,
          updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
          updated_by   VARCHAR(64)  NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS bookings (
          id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          user_id    VARCHAR(64)  NULL,
          user_name  VARCHAR(128) NULL,
          dept_name  VARCHAR(128) NULL,
          place_name VARCHAR(128) NULL,
          floor      VARCHAR(64)  NULL,
          seat       VARCHAR(64)  NULL,
          date       VARCHAR(32)  NULL,
          begin      VARCHAR(8)   NULL,
          end        VARCHAR(8)   NULL,
          KEY idx_user_id    (user_id),
          KEY idx_date       (date),
          KEY idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS bans (
          id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          user_id    VARCHAR(64)  NOT NULL UNIQUE,
          reason     VARCHAR(255) NULL,
          is_active  TINYINT(1)   NOT NULL DEFAULT 1,
          expires_at DATETIME     NULL,
          created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(64)  NULL,
          KEY idx_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))

        # 播种密钥：无 license_key 行时，用环境变量 LICENSE_KEY 兜底
        row = conn.execute(
            text("SELECT config_value FROM app_config WHERE config_key='license_key'")
        ).first()
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO app_config (config_key, config_value, updated_by) "
                    "VALUES ('license_key', :v, 'system')"
                ),
                {"v": config.LICENSE_KEY},
            )
            log.info("seeded license_key from env (empty if LICENSE_KEY unset)")

        # 播种管理员：admins 表为空且设置了 ADMIN_USERNAME/PASSWORD
        if config.ADMIN_USERNAME and config.ADMIN_PASSWORD:
            from auth import hash_password

            exists = conn.execute(
                text("SELECT 1 FROM admins LIMIT 1")
            ).first()
            if exists is None:
                conn.execute(
                    text(
                        "INSERT INTO admins (username, password_hash) "
                        "VALUES (:u, :p)"
                    ),
                    {
                        "u": config.ADMIN_USERNAME,
                        "p": hash_password(config.ADMIN_PASSWORD),
                    },
                )
                log.info("seeded default admin %s", config.ADMIN_USERNAME)
            elif conn.execute(
                text("SELECT 1 FROM admins WHERE username=:u"),
                {"u": config.ADMIN_USERNAME},
            ).first() is None:
                log.warning(
                    "ADMIN_USERNAME=%s 不存在且 admins 表非空，跳过播种",
                    config.ADMIN_USERNAME,
                )


# ---------------------------------------------------------------------------
# 密钥
# ---------------------------------------------------------------------------

def get_license_key() -> str:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT config_value FROM app_config WHERE config_key='license_key'")
        ).first()
        return (row[0] if row else "") or ""


def set_license_key(value: str, updated_by: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_config (config_key, config_value, updated_by) "
                "VALUES ('license_key', :v, :by) "
                "ON DUPLICATE KEY UPDATE config_value=:v, updated_by=:by"
            ),
            {"v": value, "by": updated_by},
        )


# ---------------------------------------------------------------------------
# 预约日志
# ---------------------------------------------------------------------------

_BOOKING_FIELDS = (
    "user_id", "user_name", "dept_name", "place_name",
    "floor", "seat", "date", "begin", "end",
)


def insert_booking(payload: dict) -> None:
    values = {f: payload.get(f, "") for f in _BOOKING_FIELDS}
    cols = ", ".join(_BOOKING_FIELDS)
    phs = ", ".join(f":{f}" for f in _BOOKING_FIELDS)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO bookings ({cols}) VALUES ({phs})"), values)


def list_bookings(page: int, page_size: int, user_id: str,
                  date_from: str, date_to: str) -> tuple:
    """返回 (total, rows)。rows 为 dict 列表。"""
    where = []
    params = {}
    if user_id:
        where.append("user_id LIKE :user_id")
        params["user_id"] = f"%{user_id}%"
    if date_from:
        where.append("date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("date <= :date_to")
        params["date_to"] = date_to
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM bookings{where_sql}"), params
        ).scalar()
        offset = (page - 1) * page_size
        rows = conn.execute(
            text(
                f"SELECT id, created_at, user_id, user_name, dept_name, place_name, "
                f"floor, seat, date, begin, end "
                f"FROM bookings{where_sql} "
                f"ORDER BY id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": offset},
        ).mappings().all()
        return total, [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 封禁
# ---------------------------------------------------------------------------

def is_banned(user_id: str) -> bool:
    if not user_id:
        return False
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM bans WHERE user_id=:u AND is_active=1 "
                "AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1"
            ),
            {"u": user_id},
        ).first()
        return row is not None


def list_bans(page: int, page_size: int, keyword: str) -> tuple:
    where = []
    params = {}
    if keyword:
        where.append("user_id LIKE :kw")
        params["kw"] = f"%{keyword}%"
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM bans{where_sql}"), params
        ).scalar()
        offset = (page - 1) * page_size
        rows = conn.execute(
            text(
                f"SELECT id, user_id, reason, is_active, expires_at, created_at, created_by "
                f"FROM bans{where_sql} ORDER BY id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": offset},
        ).mappings().all()
        return total, [dict(r) for r in rows]


def add_ban(user_id: str, reason: str, expires_at: str, created_by: str) -> int:
    """新增封禁；若该学号已存在则翻转 is_active=1 并更新原因/到期时间。返回 ban id。"""
    exp = expires_at or None
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM bans WHERE user_id=:u"), {"u": user_id}
        ).first()
        if existing is None:
            result = conn.execute(
                text(
                    "INSERT INTO bans (user_id, reason, is_active, expires_at, created_by) "
                    "VALUES (:u, :r, 1, :e, :by)"
                ),
                {"u": user_id, "r": reason, "e": exp, "by": created_by},
            )
            return result.lastrowid
        conn.execute(
            text(
                "UPDATE bans SET is_active=1, reason=:r, expires_at=:e, created_by=:by "
                "WHERE id=:id"
            ),
            {"r": reason, "e": exp, "by": created_by, "id": existing[0]},
        )
        return existing[0]


def update_ban(ban_id: int, **fields) -> None:
    allowed = {"reason", "expires_at", "is_active"}
    sets = [f"{k}=:{k}" for k in fields if k in allowed]
    if not sets:
        return
    params = {k: v for k, v in fields.items() if k in allowed}
    params["id"] = ban_id
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE bans SET {', '.join(sets)} WHERE id=:id"), params
        )


def delete_ban(ban_id: int) -> None:
    """软删：置 is_active=0。"""
    with engine.begin() as conn:
        conn.execute(text("UPDATE bans SET is_active=0 WHERE id=:id"), {"id": ban_id})


# ---------------------------------------------------------------------------
# 管理员
# ---------------------------------------------------------------------------

def get_admin(username: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, password_hash FROM admins WHERE username=:u"),
            {"u": username},
        ).first()
        return row


def create_admin(username: str, password_hash: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO admins (username, password_hash) VALUES (:u, :p)"),
            {"u": username, "p": password_hash},
        )


def touch_admin_login(username: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE admins SET last_login_at=NOW() WHERE username=:u"),
            {"u": username},
        )


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    with engine.connect() as conn:
        today = datetime.date.today().isoformat()
        today_bookings = conn.execute(
            text("SELECT COUNT(*) FROM bookings WHERE date=:d"), {"d": today}
        ).scalar()
        total_bookings = conn.execute(
            text("SELECT COUNT(*) FROM bookings")
        ).scalar()
        active_bans = conn.execute(
            text("SELECT COUNT(*) FROM bans WHERE is_active=1")
        ).scalar()
        total_bans = conn.execute(
            text("SELECT COUNT(*) FROM bans")
        ).scalar()
        return {
            "today_bookings": today_bookings,
            "total_bookings": total_bookings,
            "active_bans": active_bans,
            "total_bans": total_bans,
        }
