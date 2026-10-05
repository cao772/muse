# Stage 0.1：硬件准备基线

日期：2026-10-06。基于 `163a0ae`；Stage 0 已验收，Gateway CI #1 成功。

目标已确认：Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版。软件接口保持不变；不接 DeepSeek/MCP，不写业务固件或 GPIO 参数。本轮交付以 [板级资料](../firmware/esp32/board.md)、[到货手册](../firmware/esp32/bringup.md) 和 [官方文件锁](../firmware/esp32/vendor-artifacts.json) 为准。

已核对官方教程、仓库固定提交、原理图第 1 页，下载原理图和恢复镜像并验证其 Git blob 与 SHA-256。原始文件留在本机临时目录，不将 32MB 恢复镜像塞入项目；使用清单中的不可变 URL 可再次下载。ESP-IDF 选择 v5.5.5 为首选基线，但本轮未安装/编译；BSP 依赖范围不等于已锁定具体组件版本。

静态检查覆盖本地 Markdown 链接、官方文件清单结构和固定来源；带 `--artifacts-dir` 时额外验证下载文件大小与 SHA-256。CI 执行离线静态检查及原有 17 项测试、WebSocket 模拟器。CI 不下载大镜像、不连接设备，不代表实机通过。现有 checkout/setup-uv action 版本保持不变，其 Node 运行时迁移留作后续维护。

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 0 | Gateway / 模拟设备 / CI | 已验收，基线 163a0ae |
| 0.1 | 板型、官方资料版本、备份恢复方案 | 文档与静态核验；等待实物 |
| 1 | 先备份/原厂核验，再最小 Wi-Fi + WebSocket | 待做；必须同步增加局域网鉴权等限制 |
| 2 | 圆屏 UI + 触控 | 待做 |
| 3 | 麦克风采集 + 音频上传 | 待做 |
| 4 | STT → DeepSeek/Qwen → TTS | 待做 |
| 5 | MCP / GitHub / Dify | 待做 |

需到货补齐：实物修订、电池容量/极性、实际 Flash 探测、USB 枚举、双麦/扬声器/显示触控实测与恢复结果。本轮不声称这些项目已通过。
