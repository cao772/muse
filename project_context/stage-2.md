# Stage 2：AMOLED 与触控状态界面

日期：2026-10-07。基于 Stage 1 `fff4fa2`。范围仅屏幕、触控和连接状态；未接麦克风、扬声器、STT/LLM/TTS 或 MCP。

## 实现与来源

依据 Stage 0.1 锁定的 Waveshare 上游 `6d19f7e16fb9a3be219e9eed43ca9eb56c88d01c` 中 `examples/esp-idf/02_lvgl_demo_v9`，使用 Component Registry 托管 BSP，不在应用代码定义 GPIO。BSP 默认 466×466、旋转 0、触控 mirror_x/mirror_y；未自行猜测或调整坐标映射。

| 工具 / 组件 | 锁定版本 |
| --- | --- |
| ESP-IDF | v5.5.5 |
| waveshare/esp32_s3_touch_amoled_1_75c | 3.0.0 |
| lvgl/lvgl | 9.5.0 |
| waveshare/esp_lcd_touch_cst9217 | 2.0.0 |
| espressif/esp_lcd_co5300 | 2.2.0 |
| espressif/esp_lvgl_adapter | 0.6.4 |
| espressif/esp_websocket_client | 1.6.0 |

完整依赖、组件哈希见 [dependencies.lock](../firmware/esp32/dependencies.lock)。BSP 发布元数据指向 Waveshare-ESP32-components 提交 `010c5fb39ea7f0e996efd1f8e162cc70e569e57f`，BSP 组件哈希 `a3d1cca48e6faed9118f7b679186e498d358052afc03794e4b602541c3e0e672`。不复制厂商代码，许可证保留在下载的托管组件内。

PSRAM 使用官方示例的 OCT/80MHz 配置，启用 240MHz CPU、64KiB data cache、FreeRTOS 1000Hz；Flash 保持 Stage 1 的 32MB DIO/40MHz。不迁入官方音乐/benchmark demo、PSRAM XIP 等无关配置。BSP 传递依赖包含 codec 库，但 Muse 没有调用音频初始化/录放音 API。

## 界面与状态

- 深色圆屏，向量小脸、Muse 标题、Wi-Fi/Gateway/Auth、心跳与整体状态；使用内置英文字体，不依赖外部图片、文件系统或动画。
- `View status` 进入 Network 详情，展示设备 ID 与连接/鉴权/心跳；`Back` 返回。长设备 ID 省略显示。没有 Wi-Fi 密码、token、认证 Header、模型密钥。
- 开机即初始化显示/触控，USB RAM 配置之前显示 USB setup；之后 Connecting → Verifying → Connected。
- Connected 必须同时有 Wi-Fi、WebSocket、hello v1 和匹配 pong。断线立即清除旧鉴权/心跳，显示 Reconnecting；15 秒未收到 pong 也不再显示 Connected。
- 网络回调只更新受锁保护的状态；LVGL 自己的 200ms timer 刷新界面。主任务初始化 UI 时使用 BSP 锁，按实际 API 的 `esp_err_t` 返回值检查成功。
- 串口只输出固定 UI_STATE/UI_PAGE 和触控坐标/象限标记，不输出凭据。`UI_STATE` 是代码状态证据，不能替代人眼确认屏幕显示正确。

Stage 1 清理：USB driver 局部配置去掉 const，解决 qualifier warning。`/health` 改为 `status`、`project_stage: 2`、`protocol_version: 1`、`provider`；旧 `stage` 字段移除，WebSocket v1 不变。

## 已实际验证

- 26 项 pytest（原 Gateway 测试、health 新口径、实际 C 状态转换测试）、Ruff 与文档检查通过。
- 本机 ESP-IDF v5.5.5 编译通过，当前构建日志无 warning/error。应用 `muse_stage2.bin` 为 **1440560 字节**，2MiB 分区剩余 656592 字节；分区未扩容。
- 双份 32MiB 原厂备份烧录前再次验证一致；烧录三个区间均通过 esptool 哈希验证。没有整片擦除或 eFuse 修改；恢复本身仍未实测。
- 真机完成 USB RAM 配置 → Wi-Fi → 鉴权 WebSocket → hello v1 → 连续 3 个不同 ID 的 pong；串口记录 UI_STATE Connecting/Verifying/Connected。
- 实际停止 Gateway 5 秒后重启：真机日志 UI_STATE Reconnecting → 自动重新握手/匹配 pong → UI_STATE Connected。
- 真实 Uvicorn 的鉴权模拟器 hello/ping/pong/mock 文本通过；构建产物检查未含本地 Wi-Fi 密码或 token。
- **待实机人工验收**：屏幕可见内容、清晰度/色彩/圆形裁切、触控坐标方向、View status/Back 点击与四区域触控。不能只以编译和状态日志标记显示/触控通过。
- GitHub CI 的 Gateway 与固件构建结果以本提交运行记录为准。

## 使用与实机验收

保持 USB 连接和同路由器可互通的 2.4GHz 网络。重启后 RAM 配置消失，分别启动 Gateway 与配置脚本：

```sh
uv run muse-gateway
uv run python scripts/provision_device.py --port /dev/cu.usbmodem101 --observe-seconds 120
```

观察脚本在三次 pong 验收后额外监听 UI/触控日志 120 秒；网络 PASS 不代表触控 PASS。若板子已在线，原脚本不会重新配置；可使用 ESP-IDF monitor 观察日志，烧录或配置前先关闭串口监视器。串口名重新枚举后可能变化。

1. 开机见 Muse、USB setup；配置后 Wi-Fi/Gateway Online、Auth Verified、心跳 healthy/5s、Connected。
2. 点击 View status，看到 Network 与正确设备 ID；点击 Back 返回。记录 UI_PAGE details/home。
3. 在屏幕内部左上、右上、左下、右下分别轻点，核对 TOUCH_OK 坐标方向与对应象限；圆外无触控不算失败。
4. 停止 Gateway 至少 5 秒，屏幕应显示 Reconnecting；恢复 Gateway 后返回 Connected，串口继续匹配 pong。
5. 若黑屏、点击偏移或页面不能切换，保留现象与日志定位，不标记通过。

本轮 AP 丢失/恢复、电池供电、音频仍未验收。下一阶段在显示/触控人工验收后进入 Stage 3 双麦采集。
