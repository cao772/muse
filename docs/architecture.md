# 架构与边界

```text
设备 / scripts/simulate_device.py
              │ WebSocket v1
              ▼
      Gateway：校验、路由、错误回复
              │ TextProvider.reply(text)
              ▼
      MockProvider（当前唯一实现）
```

后续在 `integrations/llm.py` 的接口下增加 DeepSeek、Qwen 和 OpenAI-compatible 实现，并通过工厂显式选用。模型地址、模型名和密钥在具体接入时再配置，本阶段不引入云 SDK 或默认云端地址。

`integrations/mcp.py` 仅定义工具调用接口。MCP 连接、工具发现、允许列表、超时和执行授权尚未实现；没有从设备消息到工具执行的入口。GitHub、Dify 后续按实际用例接入。

固件负责采集/播放、交互与连接；Gateway 负责后续的 STT → LLM → TTS 编排。目标板已确认是 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版；驱动、引脚和初始化时序仍需依照固定版本的原理图、BSP 和实物核对，不写入猜测值。资料入口见 [板级资料](../firmware/esp32/board.md)。迁移官方 Muse SDK 前先确认上游仓库、许可证、版本和板级依赖。

Stage 1 已增加设备 token/ID 鉴权、Host/Origin 策略、连接限额和超时，以及真机 USB RAM 配置与 Wi-Fi/WebSocket 心跳。默认仍监听本机；局域网部署见 [Stage 1](../project_context/stage-1.md)。尚无持久化、流式推理或浏览器 UI。
