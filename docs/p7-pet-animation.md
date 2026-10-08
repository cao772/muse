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
