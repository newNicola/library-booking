# 数图预约 V6.0 - 河北农业大学图书馆座位预约工具

## 快速开始

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## 功能

- **手动选座** — 选择分区、日期、时段和可用座位后预约
- **多天预约** — 先按预览条件选座，再通过快捷方案自由组合多个日期与时段
- **自动 Cookie 管理** — Playwright 驱动系统 Edge 登录，自动保存 Cookie
- **快捷操作** — `F5` 刷新，`Ctrl+Enter` 提交当前预约
- **座位筛选** — 可即时切换“仅显示可用座位”，偏好会自动保存

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
├── tests/                   # 单元测试
└── requirements.txt         # 依赖
```

运行数据保存在当前用户的应用数据目录中。Windows 默认为
`%LOCALAPPDATA%\数图预约`，其中包含配置、Cookie、用户资料和滚动日志。
旧版本放在程序目录中的数据仍可自动读取。

单日预约支持选择多个时段。选择多个时段后，客户端会分别查询每个时段的座位，并只显示
所有所选时段都空闲的座位；提交时会按顺序为同一天的多个时段创建预约。

## 开发检查

```bash
pip install -r requirements-dev.txt
ruff check main.py lib server tests
pytest
cd server/frontend && npm ci && npm run build
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
