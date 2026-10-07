# 目标板与官方依据

核对日期：2026-10-06。用户选定带电池版；2026-10-07 已收货并连接 Mac，实测信息见 [接板记录](../../project_context/hardware-acceptance-2026-10-07.md)；实际 PCB 修订和电池标签待核验。

## 规格

依据 [Waveshare 产品文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75C)；以下为官方标称，不能代替实物验收。

| 项目 | 已核实资料 |
| --- | --- |
| 型号 / SKU | ESP32-S3-Touch-AMOLED-1.75C；带电池 33691，不带电池 33692 |
| SoC / 无线 | ESP32-S3R8，双核 LX7，最高 240MHz；2.4GHz Wi-Fi b/g/n、Bluetooth 5 LE |
| 内存 | 8MB PSRAM，外部 32MB NOR Flash；不得套用无 C 板的 16MB 配置 |
| 显示 | 1.75 英寸 AMOLED，466×466；CO5300，QSPI |
| 触控 | CST9217，I2C |
| 采音 / Codec | 双麦克风阵列，ES7210 ADC；ES8311 Codec |
| 放音 | 内置扬声器；原理图第 1 页 U7 标注 NS4150B 功放 |
| 电源 | AXP2101；3.7V 锂电池、1.25mm 2PIN 电池接口、充放电支持 |
| 其他 | QMI8658 六轴 IMU；PWR、BOOT 两个侧键 |
| USB | Type-C，ESP32-S3 原生 USB，用于烧录和串口日志 |

原理图的 Codec、ADC、AEC、功放、电源和 USB 区块已阅读核对；没有据此生成 GPIO 表或驱动参数。原理图固定文件及校验值见 [校验清单](vendor-artifacts.json)。

待确认项：扬声器实装阻抗/功率、麦克风具体料号、随货电池容量/极性、PCB 修订；文档概述提及 RTC，本轮不据此宣称存在已确认型号的独立 RTC 芯片。网页将电池接口称为 MX1.25，而原理图标注 PH1.25；替换电池前必须核对实物插头和正负极，不能只凭名称采购。

## 源码与工具链

上游：[waveshareteam/ESP32-S3-Touch-AMOLED-1.75C](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C)。锁定提交：`6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c`。本项目不跟随浮动 main 自动升级。

| 依据 | 结论 |
| --- | --- |
| [官方 ESP-IDF 教程](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75C/ESP-IDF) | 建议 V5.5.0 或以上，截图使用 V5.5.2；截图版本不是锁定版本 |
| [固定提交 CI](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C/blob/6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c/.github/workflows/examples.yml) | 构建矩阵 v5.5.5、v6.0.2；Muse 后续先选 v5.5.5 |
| [示例依赖](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C/blob/6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c/examples/esp-idf/02_lvgl_demo_v9/main/idf_component.yml) | `waveshare/esp32_s3_touch_amoled_1_75c: ^3.0.0`、LVGL 9.5.0；BSP 是版本范围，首次解析后必须保留依赖锁 |
| [上游 LICENSE](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C/blob/6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c/LICENSE) | 上游 README 声明 Apache-2.0；迁移组件时还须保留各组件自己的许可证和署名 |

示例路径：`examples/esp-idf/01_AXP2101` 用于电源遥测（不亮屏是预期）；`02_lvgl_demo_v9` 用于显示/触控；`05_Spec_Analyzer` 用于采音观察。扬声器参考 `examples/arduino/examples/07_ES8311`，不要混用 Arduino 与 ESP-IDF 构建参数。

Stage 0.1 仅固化资料；后续已安装 ESP-IDF v5.5.5，Stage 1 完成联网实测，Stage 2 使用上述锁定 BSP 与 LVGL 接入显示/触控。依赖与验收见 [Stage 2](../../project_context/stage-2.md)。上游构建矩阵仅说明其测试配置，不代表 Muse 或实物已通过。
