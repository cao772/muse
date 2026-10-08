# P6｜Muse 宠物小农场（离线 MVP）

P6 分支 `feature/p6-pet-garden` 基于 P5 `a33ea1e`。**只增游戏页和独立 NVS 状态机**，不改 USB 音频协议、Serena 音色、音量80、Whisper、GPT Plus、CAO、P2 Codex 或微信权限。

## 玩法与外观

原来的五页保留，新增第六页 `Pet & Garden`；可以通过左右滑动或导航箭头进入。圆形屏幕的可点击区域安排在中心安全区：
- 一只用 LVGL 几何图形原创绘制的浅蓝色小宠物，点头像进行抚摸；给零食按钮可增加 Treats 次数。短暂粉色表情即快乐状态。
- 三块独立小田地，`Plant → Water → Growing → Pick`。播种/浇水由触控操作完成，浇水后在持续上电时间内约 45 秒成熟；收获增加 Crops 计数，田地回到可播种状态。
- 未浇水的种子不会死亡；成熟后没有“枯萎/惩罚”；宠物不会饿死，不通过用户的工作绩效/联网额度计分。界面默认静音，无自动讲话。
- LVGL 每200ms已有的 UI timer 调度轻量表情切换；不新增 FreeRTOS 游戏线程，不占用音频 DMA 或网络心跳。

## 持久化

板端已有 NVS partition；**不格式化、不擦除，不修改旧键或网络凭据**。新命名空间为 `muse_pet_v1`，键 `garden`。仅保存有版本号、结构校验和轻量计数与地块阶段。由原有 ESP-IDF NVS API 校验/提交，旧版本或损坏数据使用 RAM 默认值，不能清空其他业务资料。

触摸或成熟后标记 dirty，最多每批合并提交一次（约 5 秒节流）；异常断电可能丢失最后 5 秒的点击。写失败退避10秒，不重复格式化 NVS。

**ESP32 不保证断电期间存在可信实时时钟**。再次通电若地块此前处于 Growing，计时器从本次启动重新计满45秒；不会推断关机经过了多少小时或天。在线、断 Wi-Fi 或 USB-only 时只要板子持续上电，仍可以浇水和成熟。

## 质量门

- 仓库 `tests/test_pet_native.py` 编译并执行真正的 `muse_pet_logic.c`（C11、-Wall -Wextra -Werror）。覆盖三地块完整生命周期、存档 checksum/版本/非法值、边界、互动计数和没有点击加速成长。
- Gateway 全套 Ruff/format/pytest/WebSocket 与 firmware ESP-IDF v5.5.5 均必须通过后再尝试实体板。
- 实际触摸、6页手势、页面边界、NVS 断电重启、30分钟稳定性以及 USB Speak/CDX/GPT 回归必须在用户 Mac/实体硬件上完成。**CI 编译成功不等于实机体验通过**。

## 安全边界

不导入第三方 sprite/font 文件，不触碰用户微信、M7 TraceMemo、Token，也不根据 Codex 状态自动购买、发送消息或提交代码。外部开源宠物项目只用于玩法参考；图形和状态机均为本仓自行实现。

此 PR 保持 Draft，不能自动合并 P5/P4/P3/P2 或正式 main。
