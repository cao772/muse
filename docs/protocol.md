# WebSocket 协议 v1（Stage 0）

端点：`ws://127.0.0.1:8000/ws`。UTF-8 JSON 文本帧，每条输入默认最多 16384 字节。

连接后服务端主动发送：

```json
{"type":"hello","protocol_version":1,"session_id":"随机 UUID","capabilities":["ping","text"],"provider":"mock"}
```

每次连接使用新的 session_id。请求按连接内接收顺序处理，不跨连接保存对话。客户端维护请求 ID；服务端原样回传，不做去重或重放。

| 客户端请求 | 服务端回复 |
| --- | --- |
| `{"type":"ping","id":"1"}` | `{"type":"pong","id":"1"}` |
| `{"type":"text","id":"2","text":"你好"}` | `{"type":"text","id":"2","text":"[mock] 收到：你好"}` |

`id` 为 1–64 字符字符串，`text` 为 1–4096 字符字符串；拒绝额外字段、未知消息类型和类型错误。无效 JSON/结构返回 `{"type":"error","code":"invalid_message"}`，连接保持可用。Provider 异常返回 `{"type":"error","id":"请求 ID","code":"provider_error"}`，不泄露底层异常。

二进制帧以 1003 关闭；超出字节上限以 1009 关闭。客户端应检查关闭码，修正消息后重连。Stage 0 不宣告音频能力；音频格式、分片、背压、取消和 STT/TTS 事件将在后续阶段定义。

实现和测试参考 [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) 与 [Testing WebSockets](https://fastapi.tiangolo.com/advanced/testing-websockets/)。
