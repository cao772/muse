# Muse

本地实体 AI Agent 工程。设备通过 WebSocket 连接 Mac 上的 Gateway；模型和工具集成留在 Gateway 侧，设备不保存云服务密钥。

**当前：Stage 2 屏幕与触控开发，目标为 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版。** 已完成两份整片 Flash 备份并验证一致；网络链路已实机验证；屏幕/触控验收状态见 [Stage 2 记录](project_context/stage-2.md)。Gateway 保留离线模拟能力。 不依赖 Muse Cloud，也不需要 API Key。`[mock]` 回复只是回显，不是模型推理。

## 启动

使用 [uv](https://docs.astral.sh/uv/) 管理 Python 3.12 和锁定依赖。在项目根目录运行：

```sh
uv sync --locked
uv run muse-gateway
```

默认监听 `127.0.0.1:8000`。检查健康状态：

```sh
curl http://127.0.0.1:8000/health
```

另开终端，在项目根目录模拟设备：

```sh
uv run python scripts/simulate_device.py
```

应看到 `PASS: WebSocket handshake → ping/pong → mock text reply`。配置可选：将 `.env.example` 复制为 `.env`，修改端口后给模拟器传入 `--url ws://127.0.0.1:新端口/ws`。环境变量优先于 `.env`。默认仅允许本机连接；局域网模式须配置设备 token 与明确 Host 白名单。设置鉴权后，模拟器增加 `--config .env.device`。真机步骤见 [Stage 1](project_context/stage-1.md)。

## 目录

```text
firmware/esp32/    最小 ESP-IDF 固件、板型说明、备份与恢复流程
gateway/          FastAPI、WebSocket 协议与配置
integrations/     模型接口、mock 实现与 MCP 接口预留
scripts/          设备模拟器、USB 私有配置与真机验收
tests/            协议、异常和配置测试
project_context/  范围、决策、验收和下一步
docs/             架构和通信协议
.github/workflows/ GitHub Actions
```

## 验证

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI 执行相同检查，并启动真实服务运行设备模拟器，还使用 ESP-IDF v5.5.5 编译固件。`uv.lock` 应提交版本管理；`.env`、日志、虚拟环境与固件构建输出被忽略。

## 已完成与未实现

- 已完成：健康检查、连接欢迎消息、心跳、带请求 ID 的模拟文本回复、输入校验、断线重连测试、设备模拟器、AMOLED 状态 UI 与触控页面（人工显示/触控验收待确认）、局域网 token/设备 ID 鉴权、Host/Origin 策略、连接限额与超时。
- 预留：DeepSeek / Qwen / OpenAI-compatible 文本 provider、MCP adapter。选择未实现 provider 会在启动时报错，避免静默降级。
- 后续：显示/触控人工验收、音频驱动、BLE、STT/LLM/TTS、工具调用、GitHub/Dify。当前不接收音频、不执行工具、不保留聊天历史。

协议见 [docs/protocol.md](docs/protocol.md)，当前阶段与实机步骤见 [Stage 2](project_context/stage-2.md)。

## 板子到货后

Stage 0 基线 `163a0ae` 已通过 GitHub CI。按 [到货与恢复手册](firmware/esp32/bringup.md) 执行：识别 USB → 整片 Flash 备份 → 原厂外设测试 → Stage 1 固件准备。

官方规格、版本依据和未确认项见 [板级资料](firmware/esp32/board.md)，阶段顺序见 [Stage 0.1 交接](project_context/stage-0.1.md)。最小固件与 USB 配置流程见 [Stage 1](project_context/stage-1.md)。
