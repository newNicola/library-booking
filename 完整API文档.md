# 河北农业大学图书馆预约系统 - API接口文档

## 基础信息

```
Base URL: https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace
```

## HTTP请求头

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
Origin: https://ehall.hebau.edu.cn
Referer: https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace/modules/myAppointment/index.do
Cookie: <登录后获取的Cookie>
```

---

## API接口列表

### 1. 获取楼层列表
```
URL: /modules/myAppointment/getFloorData.do
方法: POST
请求参数: 无
响应示例:
{
  "code": "0",
  "msg": "success",
  "datas": {
    "getFloorData": {
      "rows": [
        {
          "PLACE_WID": "xxx",
          "PLACE_NAME": "图书馆",
          "FLOOR_NUM": "1楼",
          "WID": "xxx"
        }
      ]
    }
  }
}
```

### 2. 获取座位列表
```
URL: /modules/myAppointment/getApplySeatDetailNew.do
方法: POST
请求参数:
  formData: {
    "BEGINNING_DATE": "2026-05-17 08:00:00",
    "ENDING_DATE": "2026-05-17 18:19:00",
    "PLACE_WID": "xxx",
    "FLOOR_NUM": "1楼"
  }

响应示例:
{
  "code": "0",
  "data": [
    {
      "WID": "xxx",
      "SEAT_NUM": "A-01",
      "IS_APPLIED": "0"  // 0=可预约, 2=已预约, 3=我的预约
    }
  ]
}
```

### 3. 预约验证
```
URL: /api/appointmentValidate.do
方法: GET
请求参数:
  begin_time: 2026-05-17 08:00:00
  end_time: 2026-05-17 09:59:00
  palce_id: xxx
  _: 1700000000000  // 时间戳

响应示例:
{
  "code": "0",
  "msg": "验证通过"
}
```

### 4. 提交预约
```
URL: /api/appointmentSave.do
方法: POST
请求参数:
  formData: {
    "WID": "uuid",
    "USER_ID": "学号",
    "USER_NAME": "姓名",
    "DEPT_CODE": "",
    "DEPT_NAME": "学院",
    "PHONE_NUMBER": "电话",
    "PALCE_ID": "xxx",
    "FLOOR_ID": "xxx",
    "SEAT_NUM": "A-01",
    "SEAT_WID": "xxx",
    "BEGINNING_DATE": "2026-05-17 08:00:00",
    "ENDING_DATE": "2026-05-17 09:59:00",
    "SCHOOL_DISTRICT_CODE": "",
    "SCHOOL_DISTRICT": "",
    "LOCATION": "",
    "PLACE_NAME": "图书馆",
    "IS_CANCELLED": "0",
    "SYNC_SCHEDULE": "0"
  }

响应示例:
{
  "code": "0",
  "msg": "预约成功"
}
```

### 5. 获取违约信息
```
URL: /api/getViolated.do
方法: GET
响应示例:
{
  "code": "0",
  "violatedCount": 0,
  "remainCount": 3,
  "defaultPeriod": "30天内"
}
```

### 6. 阅读须知
```
URL: /modules/myAppointment/T_PUBLIC_PLACE_READ_SAVE.do
方法: POST
请求参数: 空
```

### 7. 获取预约记录
```
URL: /modules/myAppointment/getMyApplyRecord.do
方法: POST
请求参数: 
  pageNumber: 1
  pageSize: 10
```

### 8. 取消预约
```
URL: /api/cancelAppointment.do
方法: POST
请求参数:
  WID: xxx
```

---

## 座位状态说明

| 状态码 | 含义 |
|--------|------|
| 0 | 可预约 |
| 1 | 不可预约 |
| 2 | 已被预约 |
| 3 | 我的预约 |

---

## 响应码说明

| code | 含义 |
|------|------|
| 0 | 成功 |
| -1 | 失败 |
| 1001 | Cookie过期 |
| 1003 | 预约冲突 |
| 1004 | 违约次数达上限 |
| 1005 | 座位已被预约 |

---

## 完整预约流程

1. **加载Cookie** → 验证有效性
2. **获取楼层列表** → 选择楼层
3. **获取座位** → 选择日期、座位
4. **检查违约** → 确保有预约资格
5. **阅读须知** → 系统要求
6. **验证预约** → 检查时间冲突
7. **提交预约** → 完成预约

