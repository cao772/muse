# 到货、备份与恢复手册（Mac）

适用：ESP32-S3-Touch-AMOLED-1.75C 带电池版。以下为可复用操作流程；本次已执行结果见 [接板记录](../../project_context/hardware-acceptance-2026-10-07.md) 与 [Stage 1](../../project_context/stage-1.md)。在仓库根目录操作，先备份再进行任何刷写；初次原厂测试不需要联网或绑定云端。

## 1. 识别 USB 与设备

记录包装型号、PCB 修订（能看到时）、电池标签、原厂界面。接支持数据传输的 USB-C 线，对比连接前后的端口：

```sh
ls /dev/cu.*
system_profiler SPUSBDataType
```

用本次实际枚举的 `/dev/cu.*` 路径替换下方示例，不自动选第一个串口；关闭占用该端口的监视器。使用独立工具环境，不改 Gateway 依赖：

```sh
export MUSE_DEVICE_PORT=/dev/cu.usbmodem实际编号
uvx --from esptool==5.1.0 esptool version
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" flash-id
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" get-security-info
```

预期芯片为 ESP32-S3、Flash 32MB。若尺寸不符或启用 Secure Boot/Flash Encryption，暂停刷写并记录输出；不要使用 `--force` 或改写 eFuse。USB 不枚举先换数据线/直连端口。官方说明下载模式为按住 BOOT 并重新上电；带电池设备拔 USB 不一定断电，需用 PWR 实际关机再开机，进入下载模式后松开 BOOT，并重新确认串口号。不要臆造不存在的 RESET 键。

## 2. 原厂整片备份

先确认 flash-id 检出的 32MB，再执行。`ALL` 由工具读取实际容量，不以镜像文件大小代替芯片容量：

```sh
umask 077
MUSE_BACKUP_DIR="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$MUSE_BACKUP_DIR"
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" --after no-reset read-flash 0 ALL "$MUSE_BACKUP_DIR/factory-full.bin"
```

保持下载模式，不启动原厂应用（应用可能写 NVS），再读取一次：

```sh
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" --after no-reset read-flash 0 ALL "$MUSE_BACKUP_DIR/factory-check.bin"
wc -c "$MUSE_BACKUP_DIR/factory-full.bin" "$MUSE_BACKUP_DIR/factory-check.bin"
cmp "$MUSE_BACKUP_DIR/factory-full.bin" "$MUSE_BACKUP_DIR/factory-check.bin"
shasum -a 256 "$MUSE_BACKUP_DIR/factory-full.bin" > "$MUSE_BACKUP_DIR/SHA256SUMS"
```

两文件各应为 33554432 字节，`cmp` 应无输出且退出码为 0；不一致时先排查重启造成的写入及通信问题，不刷写。将工具版本、设备标识、容量、日期保存在该备份目录，另复制一份到私有存储。`backups/` 已忽略，备份可能包含 Wi-Fi、配对或其他设备数据，禁止上传仓库。

### 2026-10-07 实机读取兼容性记录

本机使用 esptool 5.1.0 默认 stub 读取时出现芯片停止响应；5.1.0 `--no-stub` 与 4.12.0 stub 分别读取的前 64KiB 逐字节一致。4.12.0 已成功完成两次 32MiB 读取，逐字节一致且 SHA-256 校验通过。本次完整备份使用以下兼容路径（4.x 使用下划线命令名）：

```sh
uvx --from esptool==4.12.0 esptool.py --chip esp32s3 --port "$MUSE_DEVICE_PORT" --baud 921600 --after no_reset read_flash 0 ALL "$MUSE_BACKUP_DIR/factory-full.bin"
uvx --from esptool==4.12.0 esptool.py --chip esp32s3 --port "$MUSE_DEVICE_PORT" --baud 921600 --after no_reset read_flash 0 ALL "$MUSE_BACKUP_DIR/factory-check.bin"
```

仍需执行上面的字节数、`cmp` 和 SHA-256 检查。不要把失败或截断文件当作可恢复备份。参考 [Espressif 类似读取问题](https://github.com/espressif/esptool/issues/1155)；这是备用方案的参考，不能据此断言本机故障根因完全相同。上述备份步骤未改写 Flash 或 eFuse；后续 Stage 1 烧录另见验收记录。

## 3. 原厂功能核验

备份验证后正常重启，记录屏幕显示、触控各区域、PWR/BOOT、USB 日志、电池充电与脱离 USB 后供电。原厂界面若提供录音/播放，分别验证双麦采集和扬声器；若未提供，标记未测，不以有界面推断音频正常。之后才可用官方示例补测：电源遥测、LVGL 显示触控、频谱采音、ES8311 放音。每次换固件都保留来源版本及结果。

## 4. 恢复方案（仅需要恢复时执行）

以下写入会覆盖设备内容。正常开发不先执行整片擦除；没有可验证的备份不要试刷。

**同一块板的完整备份**：确认安全状态未变化，先检查备份 SHA-256；用本次备份目录的绝对路径替换变量，再写入并校验：

```sh
export MUSE_RESTORE_BIN=/绝对路径/factory-full.bin
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" --after no-reset write-flash 0x0 "$MUSE_RESTORE_BIN"
uvx --from esptool==5.1.0 esptool --chip esp32s3 --port "$MUSE_DEVICE_PORT" --after no-reset verify-flash 0x0 "$MUSE_RESTORE_BIN"
```

**官方出厂演示镜像**：从 [校验清单](vendor-artifacts.json) 的固定 URL 下载 `FactoryOnly-260114.bin`，先运行 `scripts/check_hardware_docs.py --artifacts-dir` 核对文件，再将 `MUSE_RESTORE_BIN` 指向它，按上述 0x0 写入、校验。该文件 33488896 字节，并非整片 33554432 字节备份；它恢复厂商演示，不保证恢复设备个性化数据，也不覆盖镜像末尾以外的区域。

官方 CI 的 `*-combined.zip` 是另一类示例固件，不等于出厂镜像。按包内 manifest 核对版本、偏移、大小和校验和；不得混用不同包的 bootloader、分区表和 app。写入成功后重启并重复显示/触控/音频/电源检查，只有这样才能标记“恢复实测通过”。

依据：[Waveshare 烧录说明](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75C/Firmware-Flashing)、[官方固件分类](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C/blob/6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c/docs/firmware.md)、[Espressif esptool 命令](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html)。恢复写入与恢复后的外设检查尚未实测；备份及 Stage 1 烧录已执行，见对应记录。

## 5. Stage 1 实机入口

在整片备份和原厂测试完成后，用 [板级资料](board.md) 固定的 ESP-IDF/上游示例建立可复现构建，再实现最小 Wi-Fi → WebSocket 客户端。网关开放到局域网之前，同步实现设备身份/token、连接限额、超时、Origin/Host 策略，不绕过现有入口强行绑定 0.0.0.0。

验收记录包括：USB 识别、双次备份一致、原厂外设结果、构建版本与日志、烧录后收到 hello、ping/pong、断网重连、日志不含凭据。显示 UI/触控排 Stage 2，采音上传 Stage 3，STT/LLM/TTS Stage 4，MCP/GitHub/Dify Stage 5。
