"""管理员鉴权：密码哈希 + JWT 签发/校验 + login_required 装饰器。"""

import datetime
import functools

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import config


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def check_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def make_token(username: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + datetime.timedelta(hours=config.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str):
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(status="fail", msg="未登录"), 401
        token = auth[len("Bearer "):].strip()
        try:
            payload = decode_token(token)
        except Exception:
            return jsonify(status="fail", msg="登录已过期，请重新登录"), 401
        g.admin_username = payload.get("sub", "")
        return fn(*args, **kwargs)
    return wrapper
