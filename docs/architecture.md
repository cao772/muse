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

固件负责采集/播放、交互与连接；Gateway 负责后续的 STT → LLM → TTS 编排。硬件驱动与具体引脚等选板后确认，不依据候选型号猜测。迁移官方 Muse SDK 前先确认上游仓库、许可证、版本和板级依赖。

当前没有设备鉴权、持久化、流式推理、配网或浏览器 UI。启动脚本限本机使用。局域网开放与真实硬件接入应同步增加鉴权、Origin 策略、连接限额和超时。
