# Muse

本地实体 AI Agent 工程。设备通过 WebSocket 连接 Mac 上的 Gateway；模型和工具集成留在 Gateway 侧，设备不保存云服务密钥。

**当前：Stage 0.1，目标为 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版，尚未实机验证。** Gateway 保持 Stage 0 的离线模拟能力。 不依赖 Muse Cloud，也不需要 API Key。`[mock]` 回复只是回显，不是模型推理。

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

应看到 `PASS: WebSocket handshake → ping/pong → mock text reply`。配置可选：将 `.env.example` 复制为 `.env`，修改端口后给模拟器传入 `--url ws://127.0.0.1:新端口/ws`。环境变量优先于 `.env`。本阶段启动命令只允许回环地址；接入真实设备前需实现设备鉴权和局域网部署配置。

## 目录

```text
firmware/esp32/    官方资料锁定、板型说明、到货备份与恢复流程
gateway/          FastAPI、WebSocket 协议与配置
integrations/     模型接口、mock 实现与 MCP 接口预留
scripts/          无硬件设备模拟器
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

CI 执行相同检查，并启动真实服务运行设备模拟器。`uv.lock` 应提交版本管理；`.env`、日志、虚拟环境与固件构建输出被忽略。

## 已完成与未实现

- 已完成：健康检查、连接欢迎消息、心跳、带请求 ID 的模拟文本回复、输入校验、断线重连测试、设备模拟器。
- 预留：DeepSeek / Qwen / OpenAI-compatible 文本 provider、MCP adapter。选择未实现 provider 会在启动时报错，避免静默降级。
- 后续：ESP-IDF 固件、屏幕/触控/音频驱动、Wi-Fi/BLE、STT/LLM/TTS、工具调用、GitHub/Dify、设备鉴权。当前不接收音频、不执行工具、不保留聊天历史。

协议见 [docs/protocol.md](docs/protocol.md)，下一阶段见 [project_context/stage-0.md](project_context/stage-0.md)。

## 板子到货后

Stage 0 基线 `163a0ae` 已通过 GitHub CI。按 [到货与恢复手册](firmware/esp32/bringup.md) 执行：识别 USB → 整片 Flash 备份 → 原厂外设测试 → Stage 1 固件准备。

官方规格、版本依据和未确认项见 [板级资料](firmware/esp32/board.md)，阶段顺序见 [Stage 0.1 交接](project_context/stage-0.1.md)。本轮没有新增可烧录固件，先固化资料和恢复路径。
