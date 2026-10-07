# Stage 1：真机 Wi-Fi / WebSocket

日期：2026-10-07。基于 Stage 0.1 `4a8e4c7`，目标板 Waveshare ESP32-S3-Touch-AMOLED-1.75C 带电池版。

## 本轮实现

- ESP-IDF v5.5.5，esp_websocket_client 1.6.0 与 `dependencies.lock`；32MB Flash、DIO/40MHz。没有屏幕/触控/音频/PMU 驱动，也没有 PSRAM 初始化。
- USB Serial/JTAG 接收一行 JSON 配置，只留 RAM，Wi-Fi 使用 RAM 存储；固件与源码不含 Wi-Fi 密码或 token。每次重启须重新运行配置脚本。
- 获取 IP 后握手，校验 hello 协议版本 1，每 5 秒发送带 ID 的 ping，只接受匹配 pong；支持 Wi-Fi/WebSocket 重连。
- Gateway 校验 Bearer token 和设备 ID，非回环监听要求 token 和明确 Host 白名单，默认拒绝浏览器 Origin，连接限额 2、空闲超时 30 秒、provider 超时 15 秒。单 worker；禁用代理头信任。
- USB 配置脚本只输出验收标记，模拟器支持本地鉴权文件，CI 增加固件编译。

## 本机配置与运行

`.env`、`.env.device` 已被 Git 忽略，设置权限 600，不提交备份/凭据/串口原始日志。按 `.env.example` 设置 Gateway：`MUSE_HOST=0.0.0.0`、随机 `MUSE_DEVICE_TOKEN`、相同的 `MUSE_DEVICE_ID`、`MUSE_ALLOWED_HOSTS` JSON 列表（Mac 的局域网 IP、localhost、127.0.0.1）。使用可信局域网 `ws://`，不用于公网。

本地 `.env.device` 字段：

```dotenv
MUSE_WIFI_SSID='填写 2.4GHz 网络名称'
MUSE_WIFI_PASSWORD='填写 Wi-Fi 密码'
MUSE_GATEWAY_URI=ws://Mac局域网IP:8000/ws
MUSE_DEVICE_ID=muse-01
MUSE_DEVICE_TOKEN=与Gateway相同的随机token
```

两终端分别运行：

```sh
uv run muse-gateway
uv run python scripts/provision_device.py --port /dev/cu.usbmodem101
```

验收脚本须看到 `WIFI_GOT_IP`、`HELLO_OK` 和 3 个不同 ID 的 `PONG_OK` 才通过；超时非零退出。Mac 可连接同一路由器的 5GHz 网络，板子须使用可互通的 2.4GHz 网络；Mac IP 变化时同步修改 URI 和 Host 白名单。

重新编译/烧录见 [固件说明](../firmware/esp32/README.md)。烧录前双份整片备份已重新比对；只写 bootloader、分区表和 app，无整片擦除、eFuse 修改。NVS 初始化失败不自动擦除原厂数据。恢复按 [恢复手册](../firmware/esp32/bringup.md)，恢复步骤尚未实测。

## 验收状态

- 本地 ESP-IDF v5.5.5 完整编译通过，app 大小 880848 字节，2MiB app 分区内。
- 烧录后 esptool 对三个写入区间哈希验证通过。
- Gateway 原有 17 项测试与新增 8 项测试共 25 项通过；真实 Uvicorn 下鉴权模拟器 hello/ping/pong/mock 文本通过。
- 真机完成 USB RAM 配置、Wi-Fi 获取 IP、鉴权 WebSocket、hello v1、3 次不同 ID 的 ping/pong。
- 实际停止并重启 Gateway，板子自动重连，再收到 hello 与匹配 pong；已验证服务断开重连，尚未通过关闭路由器验证 Wi-Fi 断网重连。
- 私有配置、原厂镜像和原始日志未纳入 Git。GitHub CI 结果以本提交运行记录为准。

## 后续

Stage 2 从锁定官方 BSP 接入屏幕和触控；之后逐项验证麦克风、扬声器、电源管理，再进入语音链路。当前没有 STT、真实模型、TTS 或工具执行能力。
