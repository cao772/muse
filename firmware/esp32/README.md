# ESP32 Stage 1

目标：**Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版**。已到货并完成两份 32MiB Flash 备份，逐字节与 SHA-256 一致。验收状态见 [Stage 1 记录](../../project_context/stage-1.md)。

最小固件使用 ESP-IDF v5.5.5、锁定的 esp_websocket_client 1.6.0，只实现 USB RAM 配置 → 2.4GHz Wi-Fi → 鉴权 WebSocket → hello → 周期 ping/pong 和断线重连。没有屏幕、触控、音频和 PMU 初始化；烧录后屏幕可能黑屏。Wi-Fi/设备 token 经 USB 下发且只留 RAM，每次重启须重新配置；构建产物不含凭据。NVS 初始化失败时不自动擦除原厂数据。

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

板级引脚、PSRAM 模式、外设电源电压仍不写入本工程；Flash 使用实测 32MB，DIO/40MHz 保守设置。`dependencies.lock` 应提交，`sdkconfig`、`build/`、`managed_components/` 不提交。
