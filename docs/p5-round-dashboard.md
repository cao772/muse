# P5｜Muse 圆屏多页面与消息中心（阶段一）

## 目标与基线

本分支从 Muse P4 `961b130` 派生，保持原 USB 录音/播放、Whisper、GPT Research、CAO P2/P3、Serena、音量80不变。仅增加**屏幕导航与只读展示**，不引入新联网、写入动作或聊天内容泄漏。

硬件：Waveshare ESP32-S3 Touch AMOLED 1.75C，466×466，LVGL 9.5。

## 五页与入口

| 序号 | 页 | 当前显示 | 数据来源 |
|---|---|---|---|
| 1 | Home | Muse/语音阶段、Wi-Fi、Gateway、认证、事项摘要 | 既有 UI/USB |
| 2 | Audio | 左右麦电平、录音进度、Speak 按钮 | ESP32 现有录音/USB |
| 3 | Codex / Projects | 执行状态、模型配置、是否需要人工反馈、任务名 | Mac USB 已传输 Codex 快照 |
| 4 | Notifications | CAO 待处理数量与可用性、微信接口状态 | Mac USB 已有 attention_count；WeChat 目前**未接入** |
| 5 | Network | Wi-Fi、Gateway、认证、心跳状态 | ESP32 现有网络状态 |

每页顶部有页码和前后切页按钮；使用 LVGL `LV_EVENT_GESTURE` 响应水平左右滑动，循环切页。触摸事件产生手势后执行 `lv_indev_wait_release`，避免误点。保留首页 View status/Audio Input，Audio Speak/Back，以及所有现有录音中禁用 Speak 逻辑。页码导航和按钮可用于实机手势不可靠时的回退入口。

**显示规则**
- CAO 数量仅从 Mac USB heartbeat 的 `attention_count` 取得；缺失、断连或超时显示 `--`，不伪称“0条消息”。
- Codex `Ended` 只表示执行进程结束，不等于正式验收完成。
- 微信当前显示 `Not linked to Muse`；不显示伪造的“未读数”。微信提醒默认无声音、不弹窗、不自动回复、更不会执行任何任务。
- 当前依旧采用 Montserrat 英文字体，不新增外置字体/字体文件。中文大屏文案需后续加入合规中文字库并验收内存与渲染。

## 微信提醒的后续数据对接门槛

CAO 原 M7 `cao#21` 仍为 Draft，TraceMemo 按明确授权的业务微信群定时采集，每天约 09:00–20:00 的30分钟采集槽，并非微信服务器实时 push。可选的下一阶段为：

1. 只取**用户明确授权群**的脱敏摘要元数据。先让 CAO 生成稳定事件 ID、可信 `received_at/observed_at`、最后同步时间、采集延迟和状态；MAC Gateway 独立私有令牌轮询。
2. 必须建立用户/设备级游标，避免把历史消息误称为“新消息”或“未读”。M7 未合入、不在线或状态过期显示 `Unavailable / Last synced`。
3. 默认只显示“有 N 条新项目消息 / 需确认事项”，不把聊天正文、发送人、群名显示在锁屏或圆屏首页。触控进入查看具体内容需明确的隐私开关。
4. 只提醒真正需要用户处理的决策/任务/阻塞/截止；去重、免打扰、焦点模式。不得未经确认转发到外部云模型。
5. 不在板端保存 WeChat 登录态、数据库、Token；不自动发送消息。不能把定时采集能力宣称为实时通知。

## 验收

- `Gateway` 原测试、静态检查、硬件文档与 ESP-IDF 固件 CI 必须全绿。
- Mac/实机：五页左右滑，页码/按钮跳转和回退；滑动后不会误触 Speak；语音 Busy 期间 Record 仍禁用；Serena 音量 80 不变。
- Wi-Fi 关闭时仍能 USB 语音及 CAO 只读计数；Wi-Fi 断线不应假装 USB 断线。
- CAO 不可用/USB 心跳超时展示未知而非0。
- 微信上线前只能显示未连接，不能冒充已推送。

本阶段**不依赖烧录前的真实交互来宣称实体通过**：静态/CI 成功是必要条件，不等于已验证触控手感、圆形边缘可达、实际字体显示、刷新流畅度。