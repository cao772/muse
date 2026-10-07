# Muse

本地实体 AI Agent 工程。设备通过 WebSocket 连接 Mac 上的 Gateway；模型和工具集成留在 Gateway 侧，设备不保存云服务密钥。

**当前：Stage 5 本地 TTS 与 ES8311 播放验证，目标为 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版。** 已完成两份整片 Flash 备份并验证一致；网络链路已实机验证；屏幕/基本触控已实机确认，双麦采集、5 秒 WAV 导出及人声清晰度已实机确认，详见 [Stage 3 记录](project_context/stage-3.md)。Gateway 保留离线模拟能力。默认 mock 不需要 API Key；真实模型需本地密钥，不依赖 Muse Cloud。`[mock]` 回复只是回显，不是模型推理。

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

- 已完成：健康检查、连接欢迎消息、心跳、带请求 ID 的模拟文本回复、输入校验、断线重连测试、设备模拟器、AMOLED 状态 UI 与触控页面（用户已确认显示及页面切换正常）、局域网 token/设备 ID 鉴权、Host/Origin 策略、连接限额与超时。
- 已实现：DeepSeek / OpenAI-compatible 文本 provider、Mac 本地 MLX Whisper STT、有界 WAV → 中文文本 → LLM 文本回复；Qwen 可使用同一兼容接口配置，尚未实测。默认 mock 保持离线。
- 后续：双麦人声/空间通道验收、语音交互整合与播放稳定性、四区域触控/显示细节补验、BLE、工具调用、GitHub/Dify。Gateway 当前不接收音频、不执行工具、不保留聊天历史。

协议见 [docs/protocol.md](docs/protocol.md)，当前 Gateway 语音步骤见 [Stage 4](project_context/stage-4.md)，固件实机步骤见 [Stage 3](project_context/stage-3.md)。

## 板子到货后

Stage 0 基线 `163a0ae` 已通过 GitHub CI。按 [到货与恢复手册](firmware/esp32/bringup.md) 执行：识别 USB → 整片 Flash 备份 → 原厂外设测试 → Stage 1 固件准备。

官方规格、版本依据和未确认项见 [板级资料](firmware/esp32/board.md)，阶段顺序见 [Stage 0.1 交接](project_context/stage-0.1.md)。最小固件与 USB 配置流程见 [Stage 1](project_context/stage-1.md)。

## 双麦输入

首页 Audio Input 显示 16kHz / 16bit / stereo 的 L/R 峰值、RMS 与 clipping。USB 可显式录制 1–5 秒 WAV，保存至忽略目录 `recordings/`；录音不进入 WebSocket JSON、Git 或模型服务。步骤及实测边界见 [Stage 3](project_context/stage-3.md)。

## Mac 单次语音处理

安装本地 STT（Apple Silicon，首次下载模型）：

```sh
uv sync --extra stt
uv run --extra stt muse-voice recordings/实际文件名.wav
uv run --extra stt muse-voice recordings/实际文件名.wav --reply
```

第一条处理命令仅本地识别，`--reply` 才发送识别文本到配置的模型。真实模式在本地 `.env` 设置 `MUSE_PROVIDER=deepseek`、`MUSE_LLM_API_KEY`、`MUSE_STT_PROVIDER=mlx-whisper`，其余见 `.env.example`。不修改 ESP32，不自动录音，不上传 WAV，不做 TTS。输出含识别文本和回复，请勿提交到 Git。

## 固定短句 → 板载扬声器

Stage 5 先独立验证播放，不自动连接 LLM 回复：

```sh
uv run muse-tts
uv run python scripts/play_audio.py recordings/tts/实际文件名.wav --port /dev/cu.usbmodem101
```

TTS 默认使用 Mac 本地 Qwen3-TTS / Serena 温柔女声，不需要 API Key；Tingting 可通过 `--provider mac-say` 手动备用；播放 WAV 为 16kHz/16bit/mono、最多 5 秒。设备经 USB 完整校验后才播放，默认音量 80/100、允许 10–80，结束静音。USB 配置和录音不能同时占用串口。实现、实机状态与验收边界见 [Stage 5](project_context/stage-5.md)。

新增无需 Key 的 Qwen3-TTS 本地女声试听：`uv run muse-tts --provider qwen-local --audition`。当前 Mac 已下载模型；其他机器先运行 `uv run python scripts/setup_local_tts.py`。用户已选定 Serena 为默认音色；`uv run muse-tts` 直接使用它，板端音量仍为 80。安装、体积、耗时和离线验证见 [离线 TTS](docs/tts-offline.md)。

## Voice MVP 自动闭环

运行 `uv run muse-talk --port /dev/cu.usbmodem101`，看到 Ready 后在屏幕按 Audio Input → Record 5s，说一句话；Mac 自动完成 Whisper → DeepSeek → Serena → USB 扬声器播放。处理期间不要重复按，等重新 Ready 再说下一句。音频不上传、录音不落盘，只有转录文本发给配置的 LLM。详细配置、阶段耗时与已知限制见 [Voice MVP](project_context/voice-mvp.md)。

Voice 体验优化：圆屏显示 Ready / Listening / Thinking / Speaking，忙时禁用录音；Whisper 与 Serena 启动预热并常驻复用。进程故障会终止并在下一轮重载，停止服务后设备显示 Host offline。验证与延迟口径见 [体验优化](project_context/voice-experience.md)。
