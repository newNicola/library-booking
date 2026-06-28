# 数图预约 V2.0 — 项目上下文（供其他 AI 工具接手）

## 项目位置
C:\Users\nicola\Desktop\数图预约\

## 项目目标
河北农业大学图书馆座位预约桌面工具。
- Python 3.13 + tkinter + ttkbootstrap
- 打包目标：pyinstaller → 单文件 exe

## 文件结构
```
数图预约/
├── main.py                  # 入口，添加 lib/ 到 sys.path，启动 BookingApp
├── lib/
│   ├── gui.py               # 主 GUI（~690行）
│   ├── api_client.py        # API 客户端（~260行）
│   └── config.py            # 配置管理
├── cookies.json             # 浏览器 Cookie（JSON 键值对）
├── user_profile.json        # 用户信息
├── requirements.txt         # requests>=2.31, ttkbootstrap>=1.10
├── 数图预约.spec            # PyInstaller 打包
└── 完整API文档.md           # 原始 API 文档（部分已过时）
```

## 已验证可用的 API
Base URL: https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace

1. POST /modules/myAppointment/getFloorData.do → 18 个场所（所有 PLACE_WID 相同）
2. POST /modules/myAppointment/getLimitFloorData.do → 12 个分区，参数：PLACE_WID, BEGINNING_DATE
3. POST /api/getApplySeatDetailNew.do → 座位列表，formData JSON，FLOOR_NUM=分区文本名
4. GET  /api/getViolated.do → 违约信息
5. POST /modules/myAppointment/T_PUBLIC_PLACE_READ_SAVE.do → 阅读须知
6. POST /api/appointmentSave.do → 提交预约

## 不可用 API（返回 404）
- /api/cancelAppointment.do
- /modules/myAppointment/getMyApplyRecord.do

## 关键 bug 修复记录（已修）
1. 座位 API 路径：/api/ 而非 /modules/myAppointment/
2. FLOOR_NUM 传分区文本名（如"三层-西区-C区"），不是 WID
3. code 字段：API 返回可能是数字 0 或字符串 "0"，用 `== 0 or == "0"` 判断
4. 提交预约字段：需要 PALCE_ID_DISPLAY, BEGINNING_DATE1, SCHOOL_DISTRICT_CODE 等
5. getLimitFloorData 返回的 dict list 和 getMyApplyRecord 返回的 dict list 在 _handle_result 中冲突，用键名区分
6. 删掉了 appointmentValidate（会报"只能预约2天内"），直接提交
7. 时间段从"上午/下午/晚上"改为 7 个精确时段

## 当前待解决问题
1. 预约后日志只显示 "正在提交预约..." 没有 "预约成功/失败" — 需要确认（可能是 cookie 过期）
2. 取消预约功能不可用（API 404）— 按钮已禁用
3. getMyApplyRecord 不可用（API 404）— 无法查看已有预约

## 用户信息
user_profile.json:
```json
{
  "USER_ID": "2023214211506",
  "USER_NAME": "贾延昭",
  "DEPT_CODE": "",
  "DEPT_NAME": "信息科学与技术学院",
  "PHONE_NUMBER": ""
}
```

## 关键代码路径
- BookingApp._handle_result() — 处理所有异步 API 结果，按数据类型分发
- ThreadedAPIClient._dispatch() — 后台线程执行 API 调用，结果放 queue
- APIClient.submit_booking() — 提交预约的核心逻辑
- SeatGrid — 座位网格组件
