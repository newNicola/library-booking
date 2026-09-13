"""
数图预约 — 密钥验证 + 预约日志 + 后台管理 服务端

单文件 Flask 服务（依赖 config/db/auth 模块）：
- POST /check_key    客户端授权密钥验证（兼容老接口，新增 user_id 封禁检查）
- POST /log_booking  客户端上报预约日志
- GET  /health       健康检查
- GET  /logs         简易 HTML 查看日志（可选 LOG_VIEW_KEY 保护，仅兜底）
- /api/*             后台管理接口（JWT 鉴权）
- /                  托管 Vue3 构建产物（SPA）

密钥存储：app_config 表（MySQL），实时修改即时生效。
"""

import hmac
import os

from flask import Flask, g, jsonify, request, send_from_directory

import auth
import config
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

app = Flask(__name__, static_folder=None)
app.config["JSON_AS_ASCII"] = False


def _json(data, code=200):
    return jsonify(data), code


# ---------------------------------------------------------------------------
# 公开接口（兼容客户端，无鉴权）
# ---------------------------------------------------------------------------

@app.route("/check_key", methods=["POST"])
def check_key():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()

    stored = db.get_license_key()
    if not stored:
        return _json({"status": "error", "msg": "服务器未配置密钥"}, 500)

    if not (key and hmac.compare_digest(key, stored)):
        return _json({"status": "fail", "msg": "密钥无效"})

    return _json({"status": "ok", "msg": "验证成功"})


@app.route("/check_ban", methods=["POST"])
def check_ban():
    """客户端提交预约前查询当前学号是否被封禁。"""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return _json({"status": "ok", "banned": False})
    if db.is_banned(user_id):
        return _json({"status": "ok", "banned": True, "msg": "该账号已被封禁，无法预约"})
    return _json({"status": "ok", "banned": False})


@app.route("/log_booking", methods=["POST"])
def log_booking():
    data = request.get_json(silent=True) or {}
    if not data.get("date") and not data.get("seat"):
        return _json({"status": "fail", "msg": "缺少预约信息"}, 400)
    try:
        db.insert_booking(data)
    except Exception as exc:
        return _json({"status": "error", "msg": f"写入失败: {exc}"}, 500)
    return _json({"status": "ok", "msg": "已记录"})


@app.route("/health", methods=["GET"])
def health():
    return _json({"status": "ok", "msg": "alive"})


@app.route("/logs", methods=["GET"])
def logs_html():
    """简易 HTML 兜底查看（后台 SPA 已取代，保留最小版）。"""
    if config.LOG_VIEW_KEY and request.args.get("key") != config.LOG_VIEW_KEY:
        return "无权访问", 403
    from html import escape

    _total, rows = db.list_bookings(1, 200, "", "", "")
    tr = "".join(
        f"<tr><td>{escape(str(r['created_at']))}</td>"
        f"<td>{escape(str(r['user_name']))}<br><small>{escape(str(r['user_id']))}</small></td>"
        f"<td>{escape(str(r['dept_name']))}</td>"
        f"<td>{escape(str(r['place_name']))}<br><small>{escape(str(r['floor']))}</small></td>"
        f"<td>{escape(str(r['seat']))}</td>"
        f"<td>{escape(str(r['date']))}<br>{escape(str(r['begin']))}-{escape(str(r['end']))}</td></tr>"
        for r in rows
    )
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>预约日志</title><style>
body{{font-family:-apple-system,'Microsoft YaHei',sans-serif;margin:20px;color:#222}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:6px 10px;text-align:left}}
th{{background:#f5f5f5}}small{{color:#888}}</style></head><body>
<h1>预约日志（共 {len(rows)} 条）</h1>
<table><tr><th>上报时间</th><th>谁</th><th>学院</th><th>哪里</th><th>座位</th><th>时间段</th></tr>{tr}</table>
</body></html>"""


# ---------------------------------------------------------------------------
# 后台管理接口（JWT 鉴权）
# ---------------------------------------------------------------------------

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = db.get_admin(username)
    if row is None or not auth.check_password(row[2], password):
        return _json({"status": "fail", "msg": "用户名或密码错误"}, 401)
    db.touch_admin_login(username)
    return _json({
        "status": "ok",
        "token": auth.make_token(username),
        "username": username,
    })


@app.route("/api/auth/me", methods=["GET"])
@auth.login_required
def api_me():
    return _json({"status": "ok", "username": g.admin_username})


@app.route("/api/key", methods=["GET"])
@auth.login_required
def api_get_key():
    return _json({"status": "ok", "key": db.get_license_key()})


@app.route("/api/key", methods=["PUT"])
@auth.login_required
def api_put_key():
    data = request.get_json(silent=True) or {}
    new_key = (data.get("key") or "").strip()
    if not new_key:
        return _json({"status": "fail", "msg": "密钥不能为空"}, 400)
    db.set_license_key(new_key, g.admin_username)
    return _json({"status": "ok", "msg": "已修改"})


@app.route("/api/logs", methods=["GET"])
@auth.login_required
def api_logs():
    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", 20, type=int)))
    user_id = request.args.get("user_id", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    total, rows = db.list_bookings(page, page_size, user_id, date_from, date_to)
    return _json({
        "status": "ok", "total": total, "page": page,
        "page_size": page_size, "rows": rows,
    })


@app.route("/api/bans", methods=["GET"])
@auth.login_required
def api_list_bans():
    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", 20, type=int)))
    keyword = request.args.get("keyword", "").strip()
    total, rows = db.list_bans(page, page_size, keyword)
    return _json({"status": "ok", "total": total, "page": page, "rows": rows})


@app.route("/api/bans", methods=["POST"])
@auth.login_required
def api_add_ban():
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return _json({"status": "fail", "msg": "学号不能为空"}, 400)
    ban_id = db.add_ban(
        user_id,
        (data.get("reason") or "").strip(),
        (data.get("expires_at") or "").strip(),
        g.admin_username,
    )
    return _json({"status": "ok", "id": ban_id})


@app.route("/api/bans/<int:ban_id>", methods=["PUT"])
@auth.login_required
def api_update_ban(ban_id):
    data = request.get_json(silent=True) or {}
    fields = {}
    if "reason" in data:
        fields["reason"] = data["reason"]
    if "expires_at" in data:
        fields["expires_at"] = data["expires_at"] or None
    if "is_active" in data:
        fields["is_active"] = 1 if data["is_active"] else 0
    db.update_ban(ban_id, **fields)
    return _json({"status": "ok"})


@app.route("/api/bans/<int:ban_id>", methods=["DELETE"])
@auth.login_required
def api_delete_ban(ban_id):
    db.delete_ban(ban_id)
    return _json({"status": "ok"})


@app.route("/api/stats", methods=["GET"])
@auth.login_required
def api_stats():
    return _json({"status": "ok", **db.get_stats()})


# ---------------------------------------------------------------------------
# 静态托管 Vue3 构建产物（SPA fallback）
# ---------------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    # API / 公开接口不在静态托管范围内
    if path.startswith(("api/", "check_key", "log_booking", "health", "logs")):
        return _json({"status": "fail", "msg": "Not Found"}, 404)

    if path and os.path.isfile(os.path.join(DIST_DIR, path)):
        return send_from_directory(DIST_DIR, path)

    index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(DIST_DIR, "index.html")
    return "前端未构建：请先运行 frontend/ 的 npm run build", 503


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
else:
    # gunicorn 等 WSGI 环境下，导入时初始化（建表 + 播种，幂等）
    try:
        db.init_db()
    except Exception as exc:  # DB 未就绪时不阻断进程启动，接口会报错
        import logging
        logging.getLogger(__name__).error("init_db failed: %s", exc)
