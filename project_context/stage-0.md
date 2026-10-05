# Stage 0 交接

建立日期：2026-10-05；交接更新：2026-10-06。

## 已确定

- 本地 Gateway + WebSocket，先用脚本模拟设备。
- 使用 Python 3.12、FastAPI、uv 锁定依赖；单项目布局，暂不拆微服务。
- 不绑定 Muse Cloud；本阶段只提供 mock 文本链路，无硬件和 API Key 依赖。
- Stage 0 时板型尚未确认；Stage 0.1 已确认为 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版，暂不实现引脚或驱动配置。

## 验收标准

- 干净环境执行 `uv sync --locked` 可安装。
- `/health` 返回 Stage 0 和 mock 状态。
- 模拟器通过真实 WebSocket 完成握手、心跳和中文回复。
- 非法消息可恢复，二进制/超大帧明确拒绝，断线后可建立新会话。
- lint、格式检查和测试通过；GitHub Actions 配置复用上述命令。

## 本地验证结果

- 使用 Python 3.12.13 创建独立 `.venv`，`uv sync --locked` 通过。
- Ruff 代码检查和格式检查通过；pytest 共 17 项通过，无警告。
- 实际启动 Uvicorn 后，`/health` 返回 `status=ok`、`stage=0`、`provider=mock`。
- 独立模拟器通过真实网络连接完成 hello、ping/pong 和中文 mock 回复。
- 模拟器显式直连 Gateway，已修复本机 SOCKS 代理环境导致本地连接失败的问题。
- `.env`、`.env.local`、虚拟环境和日志匹配忽略规则；模板 `.env.example` 可纳入版本管理。
- GitHub Gateway CI #1 已核实 completed / success，提交 `163a0ae`：[运行记录](https://github.com/cao772/muse/actions/runs/37343629908)。实体硬件、模型服务和 MCP 尚未验证。

## 下一步

按 [Stage 0.1 路线](stage-0.1.md) 继续：到货备份与外设核验 → Wi-Fi/WebSocket → 屏幕触控 → 音频上传 → STT/LLM/TTS → 工具集成。

初始化时本地仓库为空且无 remote。目标仓库为 `cao772/muse`；GitHub CI 的实际运行结果以对应提交的 Actions 记录为准。
