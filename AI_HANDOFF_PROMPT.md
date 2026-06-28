# 给其他 AI 工具的 Prompt

---

## 任务

继续开发一个河北农业大学图书馆座位预约的 Python 3 桌面程序（"数图预约 V2.0"）。项目位于 `C:\Users\nicola\Desktop\数图预约\`，完整上下文在 `PROJECT_CONTEXT.md`。

## 要求

1. **先阅读 `PROJECT_CONTEXT.md`** 了解项目结构、API、已知问题
2. **再阅读三个源代码文件** `lib/api_client.py`、`lib/gui.py`、`lib/config.py`
3. **不要重写整个项目**，在现有代码基础上修复和改进

## 当前需要做的事

### 优先级 P0：确认预约提交是否正常
- 用户报告点了"预约"后日志只显示"正在提交预约..."，没有看到"预约成功"或"预约失败"
- 可能是 cookie 过期导致 403；也可能是 `_handle_result` 没有正确处理 submit_booking 的返回结果（返回的是 `(ok, msg)` 元组，其中 ok 是 bool，msg 是 str）
- 请排查：在 `_run_booking_flow` 中的 `_flow()` 线程里，`api.submit_booking()` 返回后，`self.queue.put()` 的结果是否被 `_handle_result` 正确显示
- 如果 submit_booking 返回的 ok 是 bool 且 msg 是 str，但 `_handle_result` 中 `(ok, data)` 解包时，`data` 可能是 str msg。检查 str 分支是否正确匹配
- 建议加临时调试日志确认 submit_booking 的实际返回值

### 优先级 P1：替代取消预约方案
- 当前 `/api/cancelAppointment.do` 返回 404
- 猜测：也许可以在提交预约时用 `IS_CANCELLED: "1"` 字段，或者使用 `appointmentSave.do` 同一接口但带上预约的 WID
- 预约后从座位页面 (`getApplySeatDetailNew.do`) 可以看到 IS_APPLIED=3 的座位，其 WID 是座位 WID
- 尝试组合测试：用同样的 submit 字段 + IS_CANCELLED=1 + WID=seat_wid，看能否取消已有预约
- 如果能找到取消方式，就恢复 GUI 的取消按钮功能

### 优先级 P2：代码质量
- 清理未使用的 import 和死代码（如 `validate_appointment` 方法）
- `_handle_result` 中的类型判断链可以优化，当前靠 `isinstance(data[0], FloorInfo)` 等运行时检查，可以改为在 `_dispatch` 的结果中带一个 tag

## 注意事项
- 不要删除 `cookies.json` 和 `user_profile.json`
- 不要修改 `requirements.txt` 中已有的依赖
- API 返回的中文是 UTF-8 编码但 Python 打印时可能乱码，这是正常的（程序内 tkinter 显示没问题）
- API文档可能存在问题，如果有 API 不确认或疑似有问题的，可以提出疑问
