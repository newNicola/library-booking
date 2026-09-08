# 数图预约 — 密钥验证服务端部署

单文件 Flask 服务，接口 `/check_key`，供桌面客户端验证授权密钥。

## 快速部署（Ubuntu/Debian 云服务器）

### 1. 安装 Python 与依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# 上传 server/ 目录到服务器后：
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置密钥

密钥通过环境变量 `LICENSE_KEY` 注入（不写进代码）：

```bash
export LICENSE_KEY='你的旧key原样填这里'
```

> 老 key 继续有效：把旧 key 原样设进去即可，客户端无需任何改动。

### 3. 本地快速测试

```bash
python app.py          # 监听 0.0.0.0:5000
```

另一台机器测试：

```bash
curl -X POST http://服务器IP:5000/check_key \
  -H "Content-Type: application/json" \
  -d '{"key":"你的key"}'
# 期望返回 {"status":"ok","msg":"验证成功"}
```

### 4. 生产环境（gunicorn + systemd 常驻）

用 gunicorn 跑，避免 Flask 自带服务器：

```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

建议配 systemd 服务 `/etc/systemd/system/license.service`：

```ini
[Unit]
Description=Library Seat Booking License Server
After=network.target

[Service]
WorkingDirectory=/opt/license-server
Environment=LICENSE_KEY=你的key
ExecStart=/opt/license-server/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now license
sudo systemctl status license
```

### 5. 开放防火墙端口

云厂商控制台的**安全组**里放行 TCP `5000` 端口（若用 HTTPS 则放行 `443`）。

## 客户端配套改动

服务端部署好后，把客户端 `lib/gui.py` 里的 `_KEY_SERVER` 改成新服务器地址：

```python
_KEY_SERVER = "http://新服务器IP:5000/check_key"
```

改完需重新打包 exe（`pyinstaller 数图预约V2.0.spec`），并把新 exe 发给用户。

## 建议：绑定域名 + HTTPS

裸 IP 每次换服务器都要改客户端并重打包。建议给服务器绑个域名，并把 `_KEY_SERVER`
改成 `https://你的域名/check_key`，之后换服务器只改 DNS 解析，客户端永久不用动。

如需 HTTPS，可用 `certbot` 申请免费证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

## 安全提示

- `LICENSE_KEY` 走环境变量注入，不要把 key 提交进 git。
- `server/` 目录不要打包进发给用户的 exe。
- 客户端目前用 `http://` 明文传输 key，公网建议升级为 `https://`。
