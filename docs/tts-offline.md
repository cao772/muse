# 离线女声试听（Stage 5 补充）

2026-10-07，基于 `2986bf5`。使用 Mac 上的 Qwen3-TTS，未修改 ESP32 固件、ES8311、USB 协议或默认播放音量 80；未把 LLM 回复自动接入播放。

## 模型与运行环境

- 模型：`mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`，固定 revision `049ef77fe8816b536193c0c25f9a214d17921282`。模型仓库文件合计约 1.97GB。
- 独立 Python 3.12 环境：`~/.cache/muse-toolchains/tts`，mlx-audio 0.5.8；实测环境约 423MB，不升级 Gateway/Whisper 环境中的依赖。
- 首次安装和下载需联网、不需要 Key。合成子进程设置 HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE，模型只能从本地缓存加载。缺缓存会失败，不自动联网补下载。
- 24kHz float mono 输出经 scipy polyphase 滤波重采样至 16kHz，再转换为 int16、应用原有限幅/淡入淡出并通过 `decode_playback_wav`。超过 5 秒拒绝，不截断。生成有 token 上限和 180 秒进程超时。
- 临时文件清理，试听文件位于被 Git 忽略的 `recordings/tts/`，目录 700、文件 600。文本走 stdin、不出现在子进程参数中，无云语音请求。
- 仍默认 `mac-say` / Tingting。`qwen-local` 为显式选项；失败不会悄悄换声音。试听不会保存新的默认配置。

官方依据：[Qwen 模型与音色说明](https://github.com/QwenLM/Qwen3-TTS)、[MLX-Audio 使用说明](https://github.com/Blaizzy/mlx-audio/blob/main/docs/getting-started/quickstart-cli.md)、[模型仓库](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit)。Serena/Vivian 为原生中文女声；Sohee 为原生韩语女声，也支持中文，供对比，不保证口音与前两者相同。

## 使用

```sh
# 仅首次需要联网下载；当前 Mac 已完成
uv run python scripts/setup_local_tts.py
# 同一句话生成三个候选，不播放、不改默认值
uv run muse-tts --provider qwen-local --audition
# 单独生成
uv run muse-tts --provider qwen-local --voice Serena --text '你好，我是 Muse，有什么可以帮你的吗？'
# 沿用 Stage 5 播放器，默认音量仍为 80
uv run python scripts/play_audio.py recordings/tts/实际文件名.wav --port /dev/cu.usbmodem101
# 原有离线 fallback
uv run muse-tts --provider mac-say --voice Tingting
```

板子重启后需要按 Stage 5 文档重新下发 RAM 配置；播放时关闭串口监视器和录音接收器。

## 本机实测

Apple M5 / 16GB。测试短句：“你好，我是 Muse，有什么可以帮你的吗？”

| 候选 | 音频长度 | 完整调用耗时（含子进程/模型加载） |
| --- | --- | --- |
| Serena，温柔 | 3.680 秒 | 首次 49.233 秒；缓存热后 3.844 秒 |
| Vivian，明亮 | 4.160 秒 | 3.489 秒 |
| Sohee，柔和 | 4.960 秒 | 3.459 秒 |

首次耗时包含首次库加载/初始化；后续仍逐次启动子进程，并非已实现常驻服务。没有把这些数字当作端到端对话延迟。

三份 WAV 全部符合 16kHz/16bit/mono、5 秒限制；本地 Whisper 回识别均得到测试原句。额外使用 macOS sandbox-exec 拒绝网络访问，Serena 仍生成成功（3.844 秒），证明本次缓存下可离线合成。主观音质与默认音色仍等待用户选择；未声称本轮三份都在板载扬声器人工验收通过。

92 项 pytest 通过，保留 Stage 5 的全部 80 项。新增离线子进程参数/超时/临时目录、异常清理、输出校验、三候选生成及默认 Tingting 不变的测试。模型不进入 CI；CI 不下载大模型、不进行 GPU 推理。模型本身的速度、声线和超长文本行为以本机实测及后续试听为准。
