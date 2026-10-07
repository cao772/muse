# Voice MVP 自动闭环（Stage 5 后续）

2026-10-07，基于 Serena 默认音色基线 `aceb19a`。范围：按屏幕录音 → Mac 本地 Whisper → DeepSeek → 本地 Qwen3-TTS / Serena → USB → ES8311。没有唤醒词、全双工、流式语音、MCP 或对话历史。

## 使用

```sh
# 重启板子后先下发 RAM 配置；与录音/播放命令不要同时运行
uv run python scripts/provision_device.py --port /dev/cu.usbmodem101
# 启动自动闭环，终端显示 Ready 后再按屏幕
uv run muse-talk --port /dev/cu.usbmodem101
# 只完成一轮
uv run muse-talk --port /dev/cu.usbmodem101 --once
# 离线协议测试：mock 转录/回答，扬声器输出为静音
uv run muse-talk --port /dev/cu.usbmodem101 --once --mock
```

Mac 显示 Ready 后，板子点 Audio Input → Record 5s，说一句短话。Mac 依次显示 Transcribing / Thinking / Synthesizing / Playing，结束显示 Done 和阶段耗时，然后重新 Ready。不要在处理期间重复按录音；按 Ctrl-C 停止服务。板子继续使用已有录音/传输/播放 UI，本轮没有新增“思考中”屏幕状态。

真实模式沿用 `.env` 的 `MUSE_STT_PROVIDER=mlx-whisper`、真实 LLM provider / Key / 模型；当前为 DeepSeek。Serena 无需 Key。首次安装与模型下载见 [离线 TTS](../docs/tts-offline.md)。录音、STT 与 TTS 在 Mac 本地处理，只有转录文本发给配置的 LLM。

## 实现与边界

- `gateway/talk.py`：一轮串行处理，始终独占同一个 USB 句柄。复用 `PCMTransfer` / offset / ACK / SHA-256 验证和现有 `upload`；播放明确使用音量 80。没有改固件、GPIO、Codec、USB 命令或固件依赖锁。
- `scripts/capture_audio.py` 提取 `receive_pcm` 供已有文件导出和内存流程共用。MVP 输入必须为完整 320000 字节 / 5 秒 stereo PCM；文件导出命令仍保留。串口合并读取的残余数据保留给后续阶段。服务中途重启后，起始帧之前的旧数据/结束帧及旧导出超时仅丢弃并重新等待 BEGIN；接到新 BEGIN 后仍严格检查每块 offset 与最终 hash。
- MVP 不将录音或生成的回复 WAV 写入磁盘；临时 TTS WAV 仍使用私有临时目录并清理。默认日志只有阶段、校验元数据、耗时和分段数，没有转录文本、模型回复、凭据、PCM/base64 或任意串口日志。
- Whisper 放进可终止子进程，90 秒超时，并只用缓存模型；LLM 使用原有请求超时。TTS 使用已锁定本地模型与每次 180 秒子进程上限。不宣称常驻模型或完整一轮的统一硬时限。
- mono RMS 小于 30（int16 单位）的极静音输入直接拒绝，避免最明显的静音幻觉；这不是 VAD，也不能保证噪声/远场/方言转录正确。
- 仅 MVP 使用简短口语系统提示，原有文本接口行为不变。回复最多 120 字符；超过上限失败，不截断。按标点及最多 20 字符分段，全部合成校验后才开始播放。
- 每段仍要求 16kHz/16bit/mono、最多 5 秒。仅明确的时长超限才拆分文字重试，最小分段仍过长则失败；模型/运行环境错误不重复重试。未削弱 PCM 长度、波形限幅、hash 或设备音量限制。
- 一轮失败不自动重播、不自动发送旧转录。已播放的片段不可回滚；USB 拔出/故障需修复连接并重启服务。不要另开 provision、录音接收器或串口监视器抢占 USB。
- 首版屏幕按钮在 STT/LLM/TTS 阶段没有禁用；只在 Mac 显示 Ready 时按一次。误连按可能让设备导出等待超时，本轮没有排队/背压 UI。

## 验证

- 105 项测试通过（保留全部 92 项）。新增整轮状态顺序、静音拒绝、回复边界/文字完整分段、超时、TTS 错误不重播，以及同一 USB 句柄中完整录音 ACK/hash → mock STT/LLM/TTS → 真实上传协议的联合测试。
- 固件未改、未重新烧录，沿用 Stage 5 app 1503216 字节、2MiB 分区剩余 593936 字节；这不是本轮新增固件构建尺寸。
- 实机第一轮到达 Playing 后失败，未记录为通过；当时仅有通用错误，没有足够证据定位原因。后续增加固定 USB 错误码（拒绝码/timeout/validation），不打印串口正文。
- 随后一轮完整完成，用户确认“回复我了，就是回复的有点慢”。设备采集 80000 frames / 4994ms；STT 1.723s、LLM 1.629s、TTS 5.856s、2 段播放 6.353s，从录音接收完成到播完 15.562s。该数字不含录音/USB 导出；不能当成首音等待时间。
- 针对延迟，MVP 口语提示优先要求 18 字以内、正常分段上限从 12 提升为 20 字符，仍保留时长超限拆分与校验；新增 before_play_seconds 表示从开始转录到开始上传播放。用户第二次实机反馈“行，比上次快了”。优化后服务重启覆盖了临时日志，未保留该轮精确耗时，因此不报告数值降幅。
