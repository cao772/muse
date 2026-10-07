# ESP32 Stage 5

目标：**Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版**。已到货并完成两份 32MiB Flash 备份，逐字节与 SHA-256 一致。当前播放验证见 [Stage 5 记录](../../project_context/stage-5.md)，双麦基线见 [Stage 3](../../project_context/stage-3.md)。

固件使用 ESP-IDF v5.5.5、Waveshare BSP 3.0.0、LVGL 9.5.0 与 esp_websocket_client 1.6.0。开机初始化 AMOLED/CST9217，展示连接状态并可进入详情；保留 USB RAM 配置 → 2.4GHz Wi-Fi → 鉴权 WebSocket → hello → 周期 ping/pong 和断线重连。增加 BSP ES7210 双麦输入（16kHz/16bit/stereo/24dB），Audio Input 页面显示统计；增加 BSP ES8311 受限 USB 播放，完整校验后放音，结束静音；应用不自行改写 PMU API。Wi-Fi/设备 token 经 USB 下发且只留 RAM，每次重启须重新配置；构建产物不含凭据。NVS 初始化失败时不自动擦除原厂数据。

```sh
. /你的/esp-idf-v5.5.5/export.sh
idf.py -C firmware/esp32 build
idf.py -C firmware/esp32 -p /dev/cu.usbmodem101 flash
uv run python scripts/provision_device.py --port /dev/cu.usbmodem101
```

烧录前必须确认自己的整片备份有效，串口名可能变化。无需 erase-flash；恢复方式见下方手册。

- [板级资料与版本依据](board.md)
- [备份与恢复](bringup.md)
- [官方文件校验清单](vendor-artifacts.json)
- [Gateway 协议](../../docs/protocol.md)

板级引脚和初始化由锁定 BSP 提供，不在应用代码复制或猜测；PSRAM 按官方 LVGL 示例启用 OCT/80MHz，外设电源电压不自行改写。Flash 使用实测 32MB，DIO/40MHz 保守设置。`dependencies.lock` 应提交，`sdkconfig`、`build/`、`managed_components/` 不提交。

短录音使用 `scripts/capture_audio.py --port /dev/cu.usbmodem101 --seconds 5`，通过 USB 完整校验后保存到 Git 忽略目录。音频不走 WebSocket；运行前关闭其他串口监视器，详细验收见 Stage 3。

固定短句播放：Mac 运行 `uv run muse-tts`，再将生成的 mono WAV 交给 `scripts/play_audio.py`。默认音量 80，设备只接受 10–80、最多 5 秒音频；播放期间麦克风统计继续，显式录音请求与上传/播放互斥。接口和实机结果见 Stage 5。

Voice MVP 体验优化增加主机状态：Ready / Listening / Thinking / Speaking，非 Ready 时禁用 Record 并在录音请求入口拒绝重复触发。USB 状态每 2 秒刷新，15 秒失联显示 Host offline 并锁住录音，恢复 Ready 后解锁。现有网络、触控、音量条、PCM/hash 与音量 80 不变；详见 [体验优化](../../project_context/voice-experience.md)。
