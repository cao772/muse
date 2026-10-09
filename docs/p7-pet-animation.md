# P7｜Muse 原创像素宠物与 Codex 视觉联动

## 基线与来源
- 基于 P6 宠物农场已 CI success 的 commit `5364dd0`，只在 `feature/p7-pet-animation` 修改。
- **全部 16×16 RGB565 像素图形由仓库源码生成，无外部下载的 sprites、字体或图库许可依赖。**
- 原 P6 游戏存档结构、NVS 命名空间 `muse_pet_v1/garden` 与45秒上电时间成长行为保持不变。不需要 schema migration。

## 八种表情帧
`muse_pet_animation.[ch]` 是纯 C11、无 ESP32 和 LVGL 依赖的原生 sprite 生成器：
- Idle：陪伴
- Walk：小幅左右移动
- Sleep：久未触碰/任务空闲（30秒后）
- Happy：抚摸/喂食后的短暂开心
- Type A / Type B：已有 Codex 状态 running/starting_agent/agent_started/creating_workspace 时交替键盘帧
- Wait：已知需要用户反馈的 Codex 事件，举起提示符
- Listen：Muse 语音处理中，仅视觉表现，不额外播报

决定顺序：`需要人工反馈 > 语音处理中 > Codex运行中 > 互动开心 > 空闲睡觉 > 走动/待机`。
所有决策来自**现有 Mac USB 状态快照**，未扩大网络权限，也不会把 Agent 进程结束判为工作正式完成。
超时/Unknown 不能作为有效 Codex 工作状态；数据缺失时不绘制虚构运行/等待标识。

## 渲染策略
- 启动时生成八张 16×16 RGB565 静态图片（合计4096字节像素，不依赖 PNG/GIF/Web引擎）。
- LVGL 9.5 使用 `lv_image_dsc_t` 与 `lv_image_set_scale`，只在 pose 发生变化时替换 src；页面仍沿用200ms已有 UI timer，无新音频/游戏线程。
- 小幅步行动画只调整 Pet 容器位置；屏幕触摸和三格种植按钮不受影响。
- 未实际测试 FPS、UI 触摸阻挡、PSRAM 空闲量，实机验证前不得标记完成。

## 验收
- `tests/test_pet_native.py` 编译执行纯 C 状态模型和像素动画代码（C11、-Wall -Wextra -Werror），并覆盖七种以上帧差异、优先级、无效输入。
- Gateway Ruff/format/全量 pytest、ESP-IDF 固件 CI 必须对精确 HEAD success。
- Mac Codex 在用户许可的实体板上执行**app-only 烧录**，勿擦除 NVS/全片：对比 Idle/Walk/Sleep/Happy/Typing/Waiting/Listening，左右滑六页、三格田地、Serena 音量80、USB 音频及 Wi-Fi 断开下农场继续运行。
- 执行状态输入用受控测试任务而非生产仓库；若无法真实触发 waiting/running，标注模拟测试与真机事实的区别。

不合并 P7→P6/P5/P4/P3/P2/main，保持 Draft。

## 2026-10-09 本机外观修整与中文页

用户实机反馈原帧“有动作但有点丑”，并明确要求宠物页中文。独立子分支 `codex/p7-local-acceptance` 基于精确 P7 `0ddcd6b`，不改上游 Draft 或 main。

- 原创精灵改为 32×32 奶油色垂耳小狗：围巾、腮红、高光、脚爪与地面阴影；保留八种状态优先级。4倍整数放大，静态帧合计16 KiB（原4 KiB），不新增游戏线程。
- 宠物页使用深苔绿、奶油色、暖黄按钮，田地增加矢量嫩芽和成熟果实。保留点击/滑动处理、农场规则和 NVS schema。
- “小小农场”、心情、摸摸/零食/收获计数、喂点零食、播种/浇水/生长中/收获、说句话全部中文。嵌入 Noto Sans SC 500字重的18/24px最小字库；源、版本、SHA、许可和生成方法见 `firmware/esp32/fonts/README.md`。不把 macOS 私有字体或17MB源字体放入固件。
- 新增检查实际生成字库是否覆盖所有中文 UI 文案，连同原生 C11 状态/精灵测试，本机 **180 passed**；Ruff 和文档检查通过。
- 本机构建 app 为 `0x173ee0` / 1,523,424 字节，2 MiB app 分区剩余 `0x8c120` / 573,728 字节（27%）。不扩分区、不擦 NVS。
- 初版 P7 app-only 烧录已通过 Flash hash；用户确认“有动作”。新版中文美化 app 已 app-only 烧录，Flash hash 校验通过，启动后串口收到配置等待提示；中文清晰度、视觉效果、田地触控与断电存档需实机反馈，不能用布局预览或编译成功代替验收。

本轮保持离线等待 USB 配置：游戏已在配置前初始化。没有启用云端模型、Wi-Fi、Codex 执行或自动讲话；USB语音与存档重启仍是后续待验项。
