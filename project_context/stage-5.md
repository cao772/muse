# Stage 5：固定中文短句 → ES8311 扬声器

日期：2026-10-07，基于已验收 Stage 4 `3757edb`。范围仅为本地 TTS、受限 USB 下行及板载扬声器输出，不自动连接 LLM 回复，不做完整语音助手。

## 官方板级依据

沿用锁定 Waveshare BSP **3.0.0** 的 `bsp_audio_codec_speaker_init()`，由 BSP 创建 ES8311 DAC、I2C、PA 与 I2S 接口；不添加或猜测 GPIO。沿用 Stage 0.1 固定官方提交 `6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c` 和现有依赖锁。

ESP-IDF 5.5.5、esp_codec_dev 1.5.11、LVGL 9.5.0、CST9217 2.0.0、CO5300 2.2.0、BSP 3.0.0 均不变，无新增固件托管组件。

ES7210 与 ES8311 共用全双工 I2S。两 codec 在开始读取之前初始化，均采用 **16000Hz / 16bit / 2 slots**，播放期间不重新配置采样率/槽宽、不关闭共用 I2S。Mac 下发 mono，固件逐块复制为两个相同输出槽以适配 DAC；这不表示板子有两个独立扬声器。双麦采样/音量条继续运行，但显式录音与上传/播放互斥，避免录下自身播放声。

## TTS 与 USB 链路

- `integrations/tts.py`：`TTSAdapter`、显式静音 mock、Mac 系统 `say` / **Tingting (zh_CN)**。固定测试文本：“你好，我是 Muse，扬声器测试。”，语速参数 180。
- 文本通过 stdin 交给系统工具，不拼 shell、不放到子进程参数列表。临时音频位于 700 权限临时目录，完成/失败均清理。`afconvert` 明确转为 16kHz/16bit/mono PCM WAV，输入文本 1–80 字符，输出超过 5 秒直接拒绝，不悄悄截断。
- TTS PCM 峰值上限 16384（约 -6dBFS），头尾各最多 5ms 淡入淡出；设备播放音量限制 **10–80/100**，Mac 默认 **80**（不是声压校准值），开机与播放结束静音，超出范围会拒绝，USB 本地 `--volume` 可调。
- `muse-tts` 保存私有 WAV 到忽略目录 `recordings/tts/`，目录 700、文件 600。没有新增 API Key、云 TTS、网络音频 endpoint；STT/LLM 配置保持。
- `scripts/play_audio.py` 先校验 mono WAV 格式/长度，USB `play_begin` 声明字节数与 SHA-256，逐块至多 768 字节 PCM + base64/offset，设备每块 ACK。完整长度与 SHA-256 匹配后才通知播放任务；失败数据不会送入 codec。
- 设备最多分配 160000 字节 PSRAM（5 秒 mono），上传 5 秒无进展则清零/释放，并清理半条命令。拒绝越界、乱序、格式错误和 hash 不一致；播放后清零/释放。USB 为物理本地开发接口，无 token 认证，不用于公网或浏览器。
- 播放任务在 I2S 写入结束后等待 120ms 排空默认 DMA，再静音；完成帧数/耗时属于软件与 codec 写入证据，不能单独证明扬声器可听清。输入页新增 Receiving / Playing 状态，保留原按钮/电平页。
- WebSocket v1、鉴权、连接限额和超时不变；`/health` 的 project_stage 更新为 5。TTS 不经 WebSocket JSON。

## 构建与验证

- 本地 IDF 构建无 warning/error，固件 **1503216 字节**，2MiB app 分区占 **71.68%**，剩余 **593936 字节 / 28.32%**。比 Stage 3 增加 9904 字节，没有扩分区。
- **80 项 pytest**（Stage 4 的 59 项保留）。新增 WAV 格式/限长/截断、输出限幅与边界淡入淡出、完整 USB 上传/批量状态接收、ACK/完成长度失败不返回成功、音量边界与取消路径、子进程 stdin 与临时目录清理；测试不调用系统语音、不带真实音频或凭据。
- 两份原厂 32MiB 备份再次验证一致，SHA-256 仍为 `a2c3056182e66e9a85a99390d0453bc4c0fd61219dfc88badb97199bf9246578`。烧录段 hash 验证通过，未整片擦除或改 eFuse。
- 额外保留 Stage 3 app 回退镜像至私有 `backups/stage3-stable/muse_stage3.bin`，1493312 字节，SHA-256 `6634be597a02c76c61363dd7c39fbb763410d9166c9e0255b13c9ce93d20502f`；相同分区下可恢复 app 后重新 USB 配置，不替代整片原厂备份。
- 实机 SPEAKER_READY 确认 16kHz/2slots/16bit/volume20/静音；AUDIO_READY 与双麦统计正常。Wi-Fi → 鉴权 hello → 3 次匹配 pong 通过，UI_STATE Connected。
- 真机负向测试：超长格式、错误 SHA-256、乱序块、5 秒无进展均拒绝；半条上传命令超时后能立即接受下一次有效 begin，取消后释放。均未触发播放。
- 本地 TTS 生成 51000 mono frames / 102000 PCM 字节，**3.1875 秒**，生成约 **1.966 秒**。设备 hash 校验后播放写入完成，51000 frames，最终音量 80 回归含 DMA 排空耗时 **3237ms**。

初版 codec 音量 20 未听到；驱动默认曲线对应约 -40dB，不能将它理解为线性 20% 响度。提高到 50 后用户确认“有声音了就是有点小”；60 后用户仍希望更大，75 后用户确认“清楚，仍希望调大”，并明确选择 80；最终 Mac 默认为 80、设备上限 80（官方 ESP-IDF audio_processor 示例默认 80）。源波形仍限幅且结束静音，不改 GPIO/驱动寄存器。

排障中曾出现 USB 确认超时。补充安全元数据诊断后实际复现：`MUSE_SPK_READY` 前夹着 42 字节的半行控制台日志，严格匹配失败，尚未传音频。最终 `send_frame` 在同一 USB 驱动整块写入中附带前导换行与原有末尾换行，将确认/数据帧与残缺日志隔离；不放宽格式、offset 或 SHA-256 校验。该边界处理也用于已有录音导出，已完成录音回归。客户端错误仅给出固定错误码/预期元数据，不回显任意串口内容。

播放后的 1 秒双麦录音完整导出，16000 stereo frames，SHA-256 通过，最终帧边界修复后采集耗时 1004ms。实际 Gateway 重启时观察到 UI_STATE Reconnecting → Connected、匹配 pong 恢复，观察窗口内采音统计持续输出 18 次；`/health` 确认 stage5 / deepseek。

**实机听感**：用户确认音量 75 的短句清楚，随后明确选择默认 80。按该要求完成 80 设置；没有把前期“软件写入成功但未听到声音”记作通过。未做声压校准或长时间高音量循环测试。

**最大时长验证**：最终固件连续 3 次接收并校验 160000 字节 / 80000 mono frames 的 5 秒静音数据，播放写入均完成，含排空耗时 5048/5047/5055ms。不重复产生语音；不能以此替代多句人声的音质验收。

## 使用与验收

```sh
# 板子重启后先下发私有 RAM 配置，关闭串口监视器
uv run python scripts/provision_device.py --port /dev/cu.usbmodem101
# 本地生成固定测试短句，记下输出路径
uv run muse-tts
# 只播放这份受限 WAV；此时板子会发声
uv run python scripts/play_audio.py recordings/tts/实际文件名.wav --port /dev/cu.usbmodem101
```

监听测试短句是否完整、无明显破音；确认播放后回到 Listening，音量条仍更新，View status / Back 可用。再做短录音及 Gateway 重启检查。播放不可与录音接收器/串口监视器共占 USB。错过试听可以重复同一条播放命令，不需要重新生成或刷固件。

本轮未验收：多种语音/文本、长时间循环播放、电池功耗、扬声器声压/频响/失真、回声消除、双麦实体独立性、播放中途取消。系统 TTS 仅 macOS 可用。下一步在播放独立验收通过后再接 DeepSeek 回复。
