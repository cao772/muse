# Stage 4：Mac 本地 STT → DeepSeek 文本回复

日期：2026-10-07，基于 Stage 3 `3592bf1`。Stage 3 最终 CI run `37580132656` 的 Gateway/firmware 均已 success。

## 范围与数据流

已导出的 Stage 3 WAV → 校验 → 显式 stereo-to-mono → 本地 MLX Whisper → 中文文本 → 可选 DeepSeek → 文本回答。

没有修改 ESP32 固件、BSP、GPIO、分区或录音协议。固件仍为 Stage 3、1493312 字节，app 分区剩余 603840 字节。Gateway `/health` 的 project_stage 更新为 4，协议保持 v1；原 Wi-Fi/鉴权/hello/ping-pong/UI 链路保持。Gateway 重启后实际接受板子重新连接。

本轮是 Mac 单次 CLI 链路，**不是屏幕按键直接触发 LLM，也不是 WebSocket 音频上传**。没有 TTS、扬声器、MCP、唤醒词或持续录音。

## 实现与配置

- `integrations/stt.py`：统一 `STTAdapter`，显式 mock，以及 Apple Silicon 本地 `mlx-whisper`。输入仅接受 16kHz/16bit/stereo PCM WAV，1–80000 frames、最多 5 秒，读取上限 1MiB；拒绝格式错误、超限和截断输入。
- 转换采用 `(L + R) // 2`，先扩大为 Python 整数避免 int16 溢出；输出 mono int16，再归一化为 float32 / 32768 输入 Whisper，不经过 ffmpeg、不保存中间音频。
- 默认模型 `mlx-community/whisper-large-v3-turbo`，中文 `language=zh`、非翻译、temperature=0、无历史上下文。首轮模型下载缓存到用户 Hugging Face 缓存；下载之后仍可能执行仓库元数据检查，不能宣称断网模式已验收。
- `integrations/llm.py`：OpenAI-compatible HTTPS chat completions，DeepSeek 固定官方域名；`thinking=disabled`、非流式、默认最大 256 tokens。密钥用 SecretStr 从本地环境变量/忽略的 `.env` 读取。禁用重定向，错误不回显上游正文/异常，WebSocket 保留原 `provider_error` 映射及超时。
- DeepSeek 当前模型列表实际返回 `deepseek-flash` / `deepseek-v4-pro`；本轮使用 `deepseek-flash`。Qwen/其他兼容接口复用 adapter，但须明确填写对应 HTTPS base URL、model、key，未实测。
- API key、token、Wi-Fi 配置、录音、模型缓存均不提交。STT 不上传 WAV；只有显式 `--reply` 才将识别文本发送给配置的 LLM。CLI 结果含转录和回复，请仅用于本地查看，勿提交真实录音转录。
- `httpx2` 为运行时依赖；本地 STT 使用可选 `stt` extra，仅 Apple Silicon 安装，不把 Metal/模型下载引入 Linux CI。

本机已配置 DeepSeek、本地 STT 与 45 秒 provider 超时；模板仍默认 mock 和 15 秒，不包含真实密钥。模型/服务不可用时明确失败，不静默降级到 mock。

## 使用

```sh
uv sync --extra stt
# 只在本地识别，不调用 LLM
uv run --extra stt muse-voice recordings/实际文件名.wav
# 本地识别后，把中文文本发给 DeepSeek
uv run --extra stt muse-voice recordings/实际文件名.wav --reply
# Gateway 现有 WebSocket text 消息也可使用真实 provider
uv run muse-gateway
```

在忽略的 `.env` 配置 `MUSE_PROVIDER=deepseek`、`MUSE_LLM_API_KEY`、`MUSE_STT_PROVIDER=mlx-whisper`；其他配置见 `.env.example`。默认模型首次下载体积较大，首次耗时不能当作正常推理延迟。STT 是串行本地推理，未实现进程级强制取消/超时；不提供多用户音频服务。

## 验证

- 59 项 pytest，包含 stereo→mono 满幅/负值/不同通道、超限/格式/截断、mock WAV→STT→LLM、真实 provider 的请求结构、401/402/429/500/重定向拒绝、畸形响应、传输超时脱敏及 pipeline 超时。测试无网络、无硬件、无模型权重、无真实录音。
- Ruff lint/format 与硬件资料/链接检查通过。Stage 3 的 35 项原测试全部保留。
- 真实 DeepSeek `/models` 返回 200；直接中文文本请求成功，耗时 2.151 秒；运行中 Gateway 的鉴权 WebSocket hello→ping/pong→DeepSeek 文本回答成功，模型请求往返 1.956 秒。
- 复用已人工试听通过的 5 秒 WAV。small 模型首次有“测试”→“色”的识别错误，未人工改写；换 large-v3-turbo 后原始识别结果为 `你好Muse,这是双麦克风测试`。首次 large-v3-turbo 下载与识别总耗时 47.976 秒，不能当作纯推理时间。

同一份 5 秒 WAV 连续三次真实 pipeline 均识别为 `你好Muse,这是双麦克风测试` 并得到 DeepSeek 中文回复，没有人工改写转录：

| 次数 | STT 秒 | LLM 秒 | 合计秒 |
| --- | ---: | ---: | ---: |
| 1 | 2.874 | 2.244 | 5.118 |
| 2 | 0.429 | 2.165 | 2.594 |
| 3 | 0.429 | 2.093 | 2.522 |

三次平均 STT **1.244s**、LLM **2.167s**、合计 **3.411s**；第一次含进程内模型加载，后两次已加载 STT 均为 0.429s。均不含 ESP32 录制/USB 导出时间，不能当作整机交互延迟。MLX Whisper 0.4.3、MLX 0.32.3，Apple M5 / 16GiB。系统提示明确模型只能接收文本，模型回复不能替代硬件验收。

本轮仅一个中文短句样本，不代表广泛中文准确率；嘈杂环境、远场、方言、静音幻觉、物理双麦独立性和长时间稳定性仍未验收。

## 官方依据

- [DeepSeek 首次调用](https://api-docs.deepseek.com/zh-cn/)：官方 base URL、OpenAI-compatible chat completions、当前模型名。
- [MLX Whisper](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)：本地转录、模型仓库/本地模型路径。
