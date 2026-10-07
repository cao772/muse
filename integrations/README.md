# Integration boundaries

- `llm.py`：`TextProvider`、离线 `MockProvider`、真实 OpenAI-compatible chat completions provider。DeepSeek 使用官方 HTTPS endpoint；Qwen/其他兼容服务须明确配置自己的 base URL、model 和 key。
- `stt.py`：16kHz/16bit/stereo、最多 5 秒 WAV 校验与单声道转换，`STTAdapter`、显式 mock 和 Mac Apple Silicon 本地 MLX Whisper。没有云音频上传。
- `local_tts.py` / `local_tts_worker.py`：独立环境中的离线 MLX Qwen3-TTS，显式选择音色、缓存加载、限时合成和重采样；不需要 API Key。
- `tts.py`：本地 macOS say/Tingting，受限 mono WAV、峰值限制与淡入淡出；没有云 TTS 请求。
- `mcp.py`：工具接口预留，未启用。

默认 mock 不需要网络或 API key；真实 provider 通过本地环境变量或忽略的 `.env` 配置。错误不返回上游正文，禁用自动重定向，设置请求超时。测试使用内存 WAV 和 HTTP MockTransport，不含录音、真实凭据或计费请求。

单次本地语音入口为 `muse-voice`，步骤和能力边界见 [Stage 4](../project_context/stage-4.md)。
