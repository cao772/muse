# WebSocket 协议 v1（Stage 0 / Stage 1 / Stage 2 / Stage 3 / Stage 4 / Stage 5）

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

## Stage 1 局域网连接

非回环监听必须设置至少 32 位 ASCII 无空白设备 token 和明确 `MUSE_ALLOWED_HOSTS` JSON 列表。设备握手带 `Authorization: Bearer <token>` 与 `X-Device-ID: <id>`；缺失或错误在升级前拒绝。无 token 时 WebSocket 还会检查对端是否为本机，不能直接绑定 Uvicorn 绕过。入口关闭代理头信任，请勿启用不可信代理头。

默认拒绝携带 Origin 的浏览器连接，只有 `MUSE_ALLOWED_ORIGINS` 中明确允许的来源可用。默认最多 2 条连接，空闲 30 秒关闭 1008，provider 处理 15 秒超时返回 `provider_error`。连接计数为单进程范围，入口使用单 worker。配置见 `.env.example`。

Stage 1 使用可信局域网内的 `ws://`；没有 TLS，不用于公网。真机只验证 hello/ping/pong，文本 mock 能力仍由模拟器覆盖。

## 健康状态

`GET /health` 返回 `{"status":"ok","project_stage":5,"protocol_version":1,"provider":"mock"}`。项目阶段独立于协议版本；Stage 2 移除了旧 `stage` 字段，WebSocket v1 消息结构不变。健康接口表示 Gateway 运行状态，不代表设备已连接或外设验收通过。

Stage 3 的短 PCM 录音只经物理 USB 开发接口导出，不扩展 WebSocket JSON。Gateway 继续拒绝二进制音频帧；音频格式与 USB 边界见 [Stage 3](../project_context/stage-3.md)。

Stage 4 仅在 Mac 单次 CLI 中处理已导出的 WAV；WebSocket v1 不增加音频消息。真实 provider 的 `text` 返回模型回复，mock 仍回显；不保留聊天历史。

Stage 5 播放仍只使用物理 USB：`play_begin` 声明 mono PCM 字节数、16kHz/16bit/1ch 和 SHA-256；`play_data` 携带顺序 offset 与至多 768 字节的 base64 数据，每块 ACK；`play_end:true` 触发长度/hash 校验，成功才播放。音量限制整数 10–80，Mac 默认 80；上限 160000 PCM 字节（5 秒），5 秒上传无进展则清零/释放，`play_cancel:true` 可取消未播放的上传。播放开始后至多 5 秒，结束静音并释放，不实现播放中途取消。USB 不做设备 token 鉴权，不用于远程开放。详情见 [Stage 5](../project_context/stage-5.md)。
