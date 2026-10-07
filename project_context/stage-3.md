# Stage 3：双麦采集与短录音

日期：2026-10-07，基于 Stage 2 验收基线 `a1b3391`。范围：ES7210 双麦 PCM、实时统计/圆屏页、USB 有界短录音；没有 STT、模型、TTS、唤醒词、MCP 或扬声器播放。

## 官方依据与参数

沿用上游固定提交 `6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c` 的 `examples/esp-idf/05_Spec_Analyzer/components/bsp_extra`。官方配置为 **16000Hz、16bit、2 通道、输入增益 24dB**，本轮直接使用这些值，不采用示意图中的 48kHz。

调用锁定 BSP 3.0.0 的 `bsp_audio_codec_microphone_init()`，再用 esp_codec_dev 1.5.11 的 `open / set_in_gain / read`。不定义 GPIO、不拷贝寄存器表、不初始化 speaker codec/PA。BSP 会创建双工 I2S 通道用于时钟/数据接口，但 Muse 仅读取 ADC。ES7210 驱动默认选择 MIC1/MIC2；L/R 表示 PCM slot 0/1，**尚未确认与实体左右麦孔的空间对应**。

组件与 Stage 2 相同，`dependencies.lock` 未变：ESP-IDF 5.5.5、BSP 3.0.0、esp_codec_dev 1.5.11、LVGL 9.5.0、CST9217 2.0.0、CO5300 2.2.0、WebSocket client 1.6.0。没有新增托管组件。

## 实现

- 每次读取 1600 stereo frames（100ms / 6400 字节），独立计算 L/R 绝对峰值、RMS、RMS dBFS、达到 -32768 或 +32767 的 clipping 样本数，以及两路样本相等比例。RMS 包含 DC；WAV 分析另外报告均值及去 DC 相关系数。
- dBFS 基准为 32768，静音显示下限 -96dBFS。屏幕条形显示 -60..0dBFS，因此安静环境的低底噪可能不亮条，但数字仍更新。
- 首页保留 View status，新增 Audio Input；音频页显示两路实时电平、峰值、100ms clipping 和 Listening/Recording/Exporting/Input error，Back 返回。UI 读取锁保护的快照，音频任务不直接调用 LVGL。
- 采样块统计每 2 秒输出一次固定数字日志；不输出原始 PCM 到业务日志。平时只保留当前 RAM 块，短录音须通过 USB 命令或屏幕 Record 5s 显式触发，限制整数 1–5 秒。
- 录音缓冲按需分配 PSRAM，最多 320000 字节，完成后通过 USB 数据帧导出并清零/释放，不写设备 Flash。导出时让出 CPU，网络心跳和显示继续运行。
- 屏幕按钮避免依赖聊天倒计时，`--wait-button` 接收器等用户按键最多 180 秒；普通 `--seconds 1..5` 仍可直接触发。

- USB 开发链路使用 BEGIN / offset + base64 DATA / END，携带格式、长度与 SHA-256。Mac 先检查声明长度、分块顺序和整体 hash，每块成功后 ACK；设备等确认再发下一块，3 秒未确认中止导出。数据帧使用 USB 驱动整块阻塞发送，并持有 stdout 锁避免日志插入；控制台统一使用同一驱动。完整成功后才保存 WAV；拒绝缺块、重复、超限、格式异常和篡改。
- PCM 是专门的 USB 数据帧，不经过 WebSocket JSON、不经过 Gateway、不做连续上传。USB 无 token 鉴权，仅作为物理连接的本地开发接口。不要在导出期间使用原始串口日志重定向；提供的脚本不回显数据帧。
- 默认 WAV 存在 Git 忽略的 `recordings/`，目录 700、文件 600。音频、凭据、原厂备份均不提交；统计数字可进入验收记录。
- `/health` 项目阶段更新为 3，WebSocket 协议仍为 v1。

## 构建与软件验证

- 本地 ESP-IDF v5.5.5 编译通过，当前日志无 warning/error。
- `muse_stage3.bin` **1493312 字节**，2MiB app 分区占 **71.21%**，剩余 **603840 字节 / 28.79%**。相比 Stage 2 增加 52752 字节；来自 ADC/codec 录音路径、USB 编码和统计/UI 链接，没有扩分区。
- 35 项 pytest 通过，包含实际 C 音频统计代码的 `-Wall -Wextra -Werror` 编译/运行，覆盖静音、不同通道 RMS、满幅负值/clipping；USB 传输测试覆盖正常、丢块、重复、篡改、错误格式和超限，并模拟完整 USB/ACK/WAV 保存，验证坏 hash 不生成文件与文件权限。原状态生命周期与 Gateway 测试保留。
- 原厂双份 32MiB 备份烧录前再次验证一致，烧录各段 hash 验证通过，未整片擦除、未改 eFuse。
- 真机 AUDIO_READY 确认配置值；Wi-Fi、鉴权 hello、连续 3 次匹配 pong 通过；真实 Gateway 的模拟文本回显也通过。

## 首次实测数字

初始化后做了一次 1 秒环境样本，USB 完整接收 16000 frames / 64000 PCM 字节、SHA-256 验证通过，WAV 64044 字节，仅保存在私有 recordings 目录。

| 通道 | Peak | RMS | RMS dBFS | Clipping / 16000 samples | 均值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| L / slot 0 | 31 | 7.96 | -72.29 | 0 | -0.30 |
| R / slot 1 | 31 | 7.66 | -72.62 | 0 | -0.31 |

逐样本相等比例 7.575%，去 DC 相关系数 0.7777：两路不是逐样本复制，不能仅凭这组低电平环境数据宣称人声清晰或物理麦克风独立性已经充分验收。ADC 初始化首块可有短暂瞬态，正式录音在初始化/联网稳定后进行。

**用户已实机确认**：Audio Input 页面正常，说话时两路音量条/数字均有变化。

5 秒传输初版曾出现丢块，校验器未保存残缺 WAV。逐块 ACK 和统一控制台驱动后仍有间歇帧异常；最终改为 USB 驱动整块阻塞发送后，连续 **6 次** 5 秒导出通过，每份均为 80000 stereo frames / 320000 PCM 字节，SHA-256 验证通过。采集耗时分别为 5009/4994/4994/4994/4992/5001ms；帧数与软件耗时相符，非外部仪器校准。

## 人声实机验收

在整块串口发送修复 `a670047` 后，用户通过屏幕 Record 5s 按键录制测试短句，完整接收 80000 stereo frames / 320000 PCM 字节，SHA-256 验证通过，采集耗时 4994ms。用户本地试听后确认“挺清楚的”。录音仅留在 Git 忽略的私有 recordings 目录，不提交音频。

| 通道 | Peak | RMS | RMS dBFS | Clipping / 80000 samples |
| --- | ---: | ---: | ---: | ---: |
| L / slot 0 | 3596 | 221.63 | -43.40 | 0 |
| R / slot 1 | 3031 | 204.56 | -44.09 | 0 |

逐样本相等比例 3.59%，去 DC 相关系数 0.9787。两路均采到人声，数据并非逐样本复制；共同声源下的高相关性不能单独证明实体麦克风独立性。

**本轮已验证**：音频页和两路电平变化、按键录音、完整 WAV 导出及人声清晰度。Gateway 重启时采音统计继续更新，UI_STATE Reconnecting → Connected、匹配 pong 恢复已实际验证。

**仍未验证**：实体麦孔与 slot 对应、分别刺激麦孔的独立性验证、长时间运行、电池供电和 AP 断网恢复。

## 使用与验收

1. USB 连接板子，启动 `uv run muse-gateway`。板子重启后仍须 `uv run python scripts/provision_device.py --port /dev/cu.usbmodem101` 下发私有 RAM 配置。运行录音前关闭该串口的监视器。
2. 点 Audio Input，说话/拍手，观察两路 RMS/峰值变化及 clipping，Back/View status 仍可用；不要将 slot 名称直接当成空间左右。
3. 录制 5 秒（先启动接收器，再点屏幕 Record 5s，看到 Recording 后说测试短句）：

```sh
uv run python scripts/capture_audio.py --port /dev/cu.usbmodem101 --wait-button
uv run python scripts/analyze_audio.py recordings/实际文件名.wav
afplay recordings/实际文件名.wav
```

4. 用近距离分别轻声刺激两个麦孔并对照 L/R 统计，确认通道对应和是否两路独立；不要用物理接触产生的冲击声判断语音失真。
5. 重启 Gateway，音频统计应继续更新，界面 Reconnecting → Connected，匹配 pong 恢复。

WAV 试听只在人本地完成，不上传模型或云服务。采样率是配置值；录音帧数/耗时可交叉检查，未用外部仪器校准 I2S 时钟。AP 断网恢复、电池供电与长时间音频稳定性不在本轮验收范围。
