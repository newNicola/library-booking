# 数图预约 V2.0 - 河北农业大学图书馆座位预约工具

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 功能

- **手动选座** — 选择分区、日期、时段，点击座位预约
- **多天预约** — 一键预约多天全部 7 个时段
- **自动 Cookie 管理** — Playwright 驱动系统 Edge 登录，自动保存 Cookie

## 依赖

- Python 3.10+
- requests
- ttkbootstrap
- playwright

## 文件说明

```
数图预约/
├── main.py                  # 入口
├── lib/
│   ├── config.py            # 配置管理
│   ├── api_client.py        # API 客户端
│   └── gui.py               # GUI 主界面
├── cookies.json             # Cookie (自动生成)
├── user_profile.json        # 用户信息
└── requirements.txt         # 依赖
```

## 用户信息 (user_profile.json)

```json
{
  "USER_ID": "学号",
  "USER_NAME": "姓名",
  "DEPT_CODE": "",
  "DEPT_NAME": "学院",
  "PHONE_NUMBER": "手机号",
  "SCHOOL_DISTRICT_CODE": "1",
  "SCHOOL_DISTRICT": "东校区",
  "LOCATION": "二层、三层",
  "PLACE_NAME": "东校区数字化图书馆"
}
```
