# ESP32 固件预留目录

硬件型号等待用户确认。此前提及的 Waveshare ESP32-S3-Touch-AMOLED-1.75C 仅为候选，不构成选型结论。

Stage 0 没有 ESP-IDF 工程、引脚定义或可烧录固件，无需安装 ESP-IDF。确定板型后：

1. 核对厂家原理图、Flash/PSRAM、屏幕/触控、麦克风/扬声器及电源接口。
2. 用厂家推荐 ESP-IDF 版本跑通官方最小示例，记录版本与构建步骤。
3. 先连 Gateway 完成 hello、ping/pong，再分阶段加入 UI 和音频。
4. 将 Wi-Fi 凭据与设备令牌保存在本机或设备配置，禁止提交真实凭据。

协议入口：[../../docs/protocol.md](../../docs/protocol.md)。
