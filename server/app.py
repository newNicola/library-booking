"""
数图预约 — 密钥验证服务端

单文件 Flask 服务，提供一个 /check_key 接口，供桌面客户端验证授权密钥。

密钥验证方案：单一共享密钥
- 密钥通过环境变量 LICENSE_KEY 注入，绝不硬编码进仓库/代码。
- 老 key 继续有效：把旧 key 原样设进 LICENSE_KEY 即可，客户端无需改动。

客户端调用约定（见 lib/gui.py 的 verify_key）：
    POST /check_key  body: {"key": "..."}
    成功 -> {"status": "ok",  "msg": "验证成功"}
    失败 -> {"status": "fail", "msg": "密钥无效"}  (status 非 "ok" 即失败)
"""

import hmac
import os

from flask import Flask, jsonify, request

app = Flask(__name__)

# 单一共享密钥，从环境变量读取
LICENSE_KEY = os.environ.get("LICENSE_KEY", "").strip()


@app.route("/check_key", methods=["POST"])
def check_key():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()

    # 服务端未配置密钥：返回 500，客户端会显示 msg 内容
    if not LICENSE_KEY:
        return jsonify(status="error", msg="服务器未配置密钥"), 500

    # 用恒定时间比较，避免时序侧信道攻击
    if key and hmac.compare_digest(key, LICENSE_KEY):
        return jsonify(status="ok", msg="验证成功")

    return jsonify(status="fail", msg="密钥无效")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok", msg="alive")


if __name__ == "__main__":
    # 本地开发调试用；生产环境请用 gunicorn（见 README.md）
    app.run(host="0.0.0.0", port=5000)
