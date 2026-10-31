# 数图预约 — API 接口文档

> **项目名称：** 数图预约（河北农业大学图书馆座位预约工具）
> **基础 URL：** `https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace`
> **认证方式：** Cookie（通过 Playwright 驱动 Edge 浏览器登录 CAS 后自动获取并持久化到 `cookies.json`）
> **请求格式：** `application/x-www-form-urlencoded; charset=UTF-8`

## 目录

1. [登录与认证](#1-登录与认证)
2. [获取楼层数据](#2-获取楼层数据)
3. [获取分区（子楼层）数据](#3-获取分区子楼层数据)
4. [获取座位详情](#4-获取座位详情)
5. [查询违约记录](#5-查询违约记录)
6. [阅读公告](#6-阅读公告)
7. [提交预约](#7-提交预约)
8. [查看预约记录](#8-查看预约记录)
9. [取消预约](#9-取消预约)

---

## 1. 登录与认证

### 1.1 CAS 登录页

| 项目 | 值 |
|------|-----|
| **URL** | `https://cas.hebau.edu.cn/authserver/login?service=...` |
| **方法** | GET（浏览器跳转） |
| **用途** | 用户通过 Playwright 打开系统 Edge 浏览器，手动输入学号和密码完成 CAS 认证 |

### 1.2 Cookie 保存

登录成功后，应用从 Playwright 上下文提取 storage_state，保存到应用数据目录（Windows 默认为 `%LOCALAPPDATA%\数图预约`）的 `cookies.json`，Windows 下经 DPAPI 保护：

```json
{
  "cookies": [
    {"name": "SESSION", "value": "xxx", "domain": ".ehall.hebau.edu.cn"}
  ]
}
```

旧版扁平 JSON（`{"SESSION": "xxx"}`）仍可读取，读取后会自动迁移为上述格式。后续所有 API 请求均通过 `requests.Session` 自动携带这些 Cookie（CAS 域名 `cas.hebau.edu.cn` 的 Cookie 会被主动跳过）。

### 1.3 用户信息提取

登录后的预约页面 DOM 中，通过选择器 `.bh-headerBar-userInfo-detail` 提取用户信息，保存为 `user_profile.json`：

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

---

## 2. 获取楼层数据

获取当前图书馆可用的所有楼层/场所列表。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/modules/myAppointment/getFloorData.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |
| **请求体** | 无（空表单） |

### 响应格式

```json
{
  "code": "0",
  "datas": {
    "getFloorData": {
      "rows": [
        {
          "PLACE_WID": "xxx",
          "FLOOR_NUM": "一层",
          "WID": "yyy"
        }
      ]
    }
  }
}
```

### 响应码说明

| code | 含义 |
|------|------|
| `"0"` | 成功，返回楼层列表 |
| `"1001"` | Cookie 已过期，需重新登录 |
| 其他 | 请求失败，`msg`/`message` 字段包含错误信息 |

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `PLACE_WID` | string | 场所唯一标识（用于后续请求） |
| `FLOOR_NUM` | string | 楼层名称（如"一层"、"二层"） |
| `WID` | string | 楼层唯一标识 |

---

## 3. 获取分区（子楼层）数据

根据场所 ID 和日期，获取该场所下的分区信息（如"东侧"、"西侧"等）。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/modules/myAppointment/getLimitFloorData.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `PLACE_WID` | `abc123` | 场所 ID（来自楼层数据） |
| `PLACE_WID1` | `abc123` | 同 `PLACE_WID` |
| `BEGINNING_DATE` | `2026-06-28 08:00` | 开始日期+时间 |
| `BEGINNING_DATE1` | `2026-06-28 08:00` | 同 `BEGINNING_DATE` |
| `ENDING_DATE` | `2026-06-28 09:59` | 结束日期+时间 |
| `ENDING_DATE1` | `2026-06-28 09:59` | 同 `ENDING_DATE` |

### 响应格式

```json
{
  "code": "0",
  "datas": {
    "getLimitFloorData": {
      "rows": [
        {
          "FLOOR_NUM": "二层、三层",
          "PLACE_WID": "abc123",
          "WID": "zzz"
        }
      ]
    }
  }
}
```

### 响应码说明

| code | 含义 |
|------|------|
| `"0"` 或 `0` | 成功，返回分区列表 |
| `"1001"` | Cookie 已过期 |
| 其他 | 失败 |

---

## 4. 获取座位详情

获取指定分区、日期、时段的座位状态。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/api/getApplySeatDetailNew.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `formData` | `{"BEGINNING_DATE":"2026-06-28 08:00","ENDING_DATE":"2026-06-28 09:59","PLACE_WID":"abc","FLOOR_NUM":"二层、三层"}` | JSON 字符串，URLEncoded 后提交 |

#### formData 内部字段

| 字段 | 格式 | 说明 |
|------|------|------|
| `BEGINNING_DATE` | `YYYY-MM-DD HH:mm` | 开始时间 |
| `ENDING_DATE` | `YYYY-MM-DD HH:mm` | 结束时间 |
| `PLACE_WID` | string | 场所 ID |
| `FLOOR_NUM` | string | 分区名称（子楼层） |

### 响应格式

```json
{
  "code": "0",
  "data": [
    {
      "WID": "seat001",
      "SEAT_NUM": "2001",
      "IS_APPLIED": "0"
    }
  ]
}
```

### 响应码说明

| code | 含义 |
|------|------|
| `"0"` 或 `0` | 成功，返回座位列表 |
| `"1001"` | Cookie 已过期 |
| 其他 | 失败 |

### 座位状态字段

| 字段 | 说明 |
|------|------|
| `WID` | 座位唯一标识 |
| `SEAT_NUM` | 座位编号 |
| `IS_APPLIED` | `"0"`=可用，`"3"`=已预约他人，其他值=不可用 |

---

## 5. 查询违约记录

获取用户的违规预约次数和剩余可预约次数。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/api/getViolated.do` |
| **方法** | GET |

### 响应格式

```json
{
  "code": "0",
  "violatedCount": 1,
  "remainCount": 2,
  "defaultPeriod": ""
}
```

### 响应码说明

| code | 含义 |
|------|------|
| `"0"` 或 `0` | 成功，返回违约信息 |
| `"1001"` | Cookie 已过期 |
| 其他 | 失败 |

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `violatedCount` | int | 已违约次数 |
| `remainCount` | int | 剩余可预约次数 |
| `defaultPeriod` | string | 默认周期 |

---

## 6. 阅读公告

标记用户已阅读预约相关公告/须知。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/modules/myAppointment/T_PUBLIC_PLACE_READ_SAVE.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `formData` | 空对象 `{}` | 无实际数据 |

### 响应

无结构化响应体，HTTP 200 即表示成功。

---

## 7. 提交预约

提交座位预约请求。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/api/appointmentSave.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `formData` | JSON 字符串 | 预约数据的 URLEncoded JSON |

#### formData 内部字段

| 字段 | 格式 | 说明 |
|------|------|------|
| `WID` | `""` | 留空 |
| `USER_ID` | 学号 | 用户学号 |
| `USER_NAME` | 姓名 | 用户姓名 |
| `DEPT_CODE` | 字符串 | 学院编码（可为空） |
| `DEPT_NAME` | 字符串 | 学院名称 |
| `PHONE_NUMBER` | 字符串 | 手机号 |
| `PALCE_ID` | PLACE_WID | 场所 ID |
| `PALCE_ID_DISPLAY` | 场所名 | 场所显示名称 |
| `BEGINNING_DATE` | `YYYY-MM-DD HH:MM:SS` | 开始时间 |
| `ENDING_DATE` | `YYYY-MM-DD HH:MM:SS` | 结束时间 |
| `SCHOOL_DISTRICT_CODE` | `"1"` | 校区编码 |
| `SCHOOL_DISTRICT` | `"东校区"` | 校区名称 |
| `LOCATION` | `"二层、三层"` | 位置描述 |
| `PLACE_NAME` | 场所名 | 场所名称 |
| `IS_CANCELLED` | `"0"` | 未取消 |
| `BEGINNING_DATE1` | `MM-DD HH:MM:SS` | 简写开始时间 |
| `ENDING_DATE1` | `MM-DD HH:MM:SS` | 简写结束时间 |
| `FLOOR_ID` | WID | 楼层/分区标识 |
| `SEAT_NUM` | `"2001"` | 座位编号 |
| `SEAT_WID` | 座位 WID | 座位唯一标识 |
| `SYNC_SCHEDULE` | `"0"` | 同步标志 |

### 响应格式

```json
{
  "code": 0,
  "msg": "预约成功"
}
```

### 响应码说明

| code | 含义 |
|------|------|
| `0` 或 `"0"` | 预约成功，`msg` 包含成功消息 |
| 非 0 | 预约失败，`msg` 包含错误原因 |

### 错误处理

- 如果 HTTP 状态码不是 200，直接返回网络错误
- 如果响应不是合法 JSON，返回解析错误

---

## 8. 查看预约记录

获取指定日期的预约记录，GUI 的记录查看入口即用此接口。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/modules/myAppointment/getMyAppointmentRecord.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `querySetting` | JSON 字符串 | 过滤条件数组，见下 |
| `pageSize` | `"10"` | 每页条数 |
| `pageNumber` | `"1"` | 页码 |

`querySetting` 为过滤条件数组的 JSON 字符串，至少包含预约日期条件，可选附加是否取消条件：

```json
[
  {"name": "APPLY_DATE", "caption": "预约日期", "linkOpt": "AND", "builderList": "cbl_String", "builder": "equal", "value": "2026-10-31"},
  {"name": "IS_CANCELLED", "caption": "是否取消", "linkOpt": "AND", "builderList": "cbl_String", "builder": "equal", "value": "0"}
]
```

其中 `IS_CANCELLED` 省略表示全部，`"0"` 表示未取消，`"1"` 表示已取消。

### 响应格式

```json
{
  "code": "0",
  "datas": {
    "getMyAppointmentRecord": {
      "totalSize": 3,
      "rows": [
        {
          "WID": "xxx",
          "FLOOR_ID_DISPLAY": "二层、三层",
          "SEAT_WID_DISPLAY": "2001",
          "BEGINNING_DATE": "2026-10-31 08:00",
          "ENDING_DATE": "2026-10-31 09:59",
          "IS_CANCELLED_DISPLAY": "否",
          "IS_VIOLATED_DISPLAY": "否",
          "CREATED_AT": "2026-10-30 20:00:00"
        }
      ]
    }
  }
}
```

### 响应码说明

| code | 含义 |
|------|-----|
| `"0"` 或 `0` | 成功 |
| `"1001"` | Cookie 已过期，需重新登录 |
| 其他 | 失败 |

---

## 9. 取消预约

取消单条预约；GUI 的批量取消即按顺序逐条调用本接口并汇总结果。

| 项目 | 值 |
|------|-----|
| **URL** | `{BASE_URL}/api/appointmentCancel.do` |
| **方法** | POST |
| **Content-Type** | `application/x-www-form-urlencoded` |

### 请求参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `formData` | JSON 字符串 | 见下 |

#### formData 内部字段

| 字段 | 格式 | 说明 |
|------|------|------|
| `WID` | 预约记录 WID | 要取消的预约唯一标识（来自第 8 节的记录） |
| `ENDING_DATE` | `YYYY-MM-DD HH:MM:SS` | 该预约的结束时间 |

### 响应格式

```json
{
  "code": 0,
  "msg": "取消成功"
}
```

### 响应码说明

| code | 含义 |
|------|-----|
| `0` 或 `"0"` | 取消成功 |
| `"1001"` | Cookie 已过期，需重新登录 |
| 其他 | 取消失败，`msg` 包含失败原因 |

### 批量取消说明

批量取消没有单独的服务端接口：客户端按顺序逐条调用单条取消，任一条返回 `1001` 即整体按 Cookie 过期处理；结束时汇总成功条数与失败原因（失败原因最多展示前 3 条）。

---

## 公共请求头

所有 API 请求均携带以下 Headers：

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
Origin: https://ehall.hebau.edu.cn
Referer: https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace/modules/myAppointment/index.do
```

---

## 错误码速查

| code | 来源接口 | 含义 |
|------|---------|------|
| `"0"` / `0` | 所有 | 成功 |
| `"1001"` | 所有 | Cookie 已过期，需重新登录 |
| 其他数字/字符串 | 各接口 | 业务错误，详见 `msg` 字段 |

---

## Cookie 域名说明

| 域名 | 是否使用 | 说明 |
|------|---------|------|
| `cas.hebau.edu.cn` | 否 | CAS 认证 Cookie，被主动跳过 |
| `.ehall.hebau.edu.cn` | 是 | 所有业务 API 所需的认证 Cookie |
