# ESP32 固件准备

已确认目标：**Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版**。不是无 C 的 1.75 型号。板子未到货，未编译或烧录 Muse 固件、未实机验证。

- [板级资料与版本依据](board.md)：规格、官方源码固定提交、BSP、未确认项。
- [到货、备份、恢复与验收](bringup.md)：Mac 上识别 USB、整片备份、原厂功能验证及 Stage 1 入口。
- [官方文件校验清单](vendor-artifacts.json)：原理图与出厂镜像的固定 URL、大小、SHA-256。
- [Gateway 协议](../../docs/protocol.md)：当前 hello / ping / pong / text / error。

本轮只固化资料，不建立未经编译验证的 ESP-IDF 空壳，也不复制完整厂商 SDK。后续从锁定上游的最小示例入手，以 ESP-IDF v5.5.5 为首选基线；外设引脚、PSRAM 模式、Flash 时序及 PMU 电压均未写进本项目配置。

官方文件可下载到仓库外目录；从仓库根目录运行 `uv run python scripts/check_hardware_docs.py --artifacts-dir /绝对路径` 核验。整片 Flash 备份可能含设备状态或凭据，只保存在 `backups/` 或仓库外，不提交版本管理。
