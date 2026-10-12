# P9｜Codex 多项目圆屏驾驶舱｜开发基线与验收契约

> **状态：方案基线；本提交只有文档，没有实现新 API 或实体画面。** 不得将新增 Draft PR 视为功能完成。

## 背景

用户 2026-10-12 确认 P9/P10 的主要用途：**在实体 Muse 466×466 圆屏上查看大量 Codex 项目与进度。** P9 只读“多个项目有哪些任务正在运行/等待/失败”；P10 基于选中的项目和任务做受控查询/反馈/继续。现有 P8 `feature/p8-wechat-notifications` HEAD `ee0b6ba4b42e588672b6c477bf1fb7646e79cdfc` 已保留、无 merge。

## 现有代码入口与复用范围

| 组件 | 入口 | 现状与改造 |
|---|---|---|
| ESP32 LVGL9 | `firmware/esp32/main/muse_ui.c` | `PAGE_TASK` 改多项目总览；详情按选中项目/任务展示；不得破坏 P8 `PAGE_INBOX`、十一及农场 |
| Mac Gateway | `gateway/talk.py` `send_state/poll_execution` | 现在只推单个活跃 execution；新增独立只读 `poll_codex_board` 和受限快照帧 |
| Muse CAO client | `integrations/cao.py` | 增加受控 `codex_board` 调用、严格schema校验，失败显示 unknown/stale |
| CAO P9 | [cao#35](https://github.com/cao772/cao/issues/35) | 授权项目+仓库的多任务摘要 API；不能把非授权全局数据直接推设备 |
| 已有操作 | `integrations/execution_agent.py` | 保留 P2 单 UUID inspect/feedback/continue，P9 不扩大写权限 |

## 视觉/操作设计

- 顶部“CODEX 项目总览”：已接入项目数 / 运行中 / 待确认 / 异常，源不可用时计数改“--”并标记最后成功时间。
- 中部项目卡：单屏 2–3 条，固定高对比中文短名称、最新一个任务短标题和状态图标；以 “等待处理 → 失败/阻塞 → 运行 → 最近更新” 排序。
- 底部页码与切换：长清单分页（默认允许至少50项目，不一次性绘制全部）；轻触项目打开详情；返回保留列表页位置，左右全局翻页仍有效。
- 详情页展示任务清单（最多5）、最近真实进度短句、实际通过/失败测试数、最新可信时间、来源标签。未知/失联不得显示 0 项或虚构百分比。
- **先不放任何“执行/继续”快捷按钮**：P10 需独立确认设计与准入门，避免触摸误操作。
- 目前七页：home/audio/tasks/inbox/shiyi/garden/network。尽量复用 tasks 页，详情用独立视图/分层，不在顶层堆新页。
- 中文字体必须复用现有字库或补充极小字集；固件 2MiB 应用分区余约 16%，严禁新增高成本动画 atlas。

## 源分层与状态语义

1. 已登记项目目录（CAO/project inventory）**不是** Codex 运行任务清单。
2. P2 `personal_enabled` 下的受控 execution 有明确 ID/工作区/状态，可提供多任务详情，但现有单执行 API 不足以跨项目列出。
3. 非 Muse 发起的 Codex Mac CLI/桌面会话、其它项目工作树必须额外**在本机授权并主动登记**后才可能加入读源；当前不能假装已经全部覆盖。
4. 每个记录必须带 `source`、`observed_at`、`freshness`。运行中/等待/结束未验收/失败/未知/过期是不同状态。Codex 的 `finished`/task.finished 不等于正式完成。
5. 对同一 project+repo+execution/session 做稳定去重。计数同时显示 “已接入/已观测”，明确未覆盖项目。

## 数据协议建议（经 API/安全审查后最终确定）

Gateway → 板端新的 `codex_board` 帧仅包含有界字段：`status`、`observed_at`、`registered_project_count`、`observed_project_count`、`running_count`、`needs_input_count`、`failed_count`、`page_index`、`page_count`、`projects[<=3]`，项目内仅 `id_alias`、`short_name`、`status`、`latest_task_title`、`age_seconds`。数据层可以缓存更多，但**设备帧与显示缓存都应有界**。

CAO → Gateway 私有只读 `GET /api/v1/personal-agent/codex-board` 支持项目列表及每项目有界任务，按独立 X-Muse-Token、显式用户/设备/项目/仓库授权隔离。不返回 prompt、终端输出、私有路径/凭据。数据不可用显示 unknown/unavailable，不能回退到不安全全局接口。

## 分工与验收路径

1. CAO 先实作授权多项目索引与 API，模拟30–50个项目测分页、源断联、跨scope、撤权。
2. Muse Gateway 做严格解析、缓存/轮询、帧大小上限；不阻塞USB Voice/STT/TTS，不能把模拟任务说成真实。
3. LVGL 原 Tasks 页上实现可触摸多项目列表，详情和回退，保持P8消息/宠物/农场不变。
4. 精确 HEAD 测试/Gateway CI/固件 CI 全绿；对真实已授权 CAO 多项目做端到端验证；app-only刷写前备份NVS，禁止全片擦写。
5. **P10** 按 [Muse#17](https://github.com/cao772/muse/issues/17) 的受控操作门槛推进，不能为了展示进度而扩大 Codex 修改权限。

相关任务：[Muse#16](https://github.com/cao772/muse/issues/16)、[Muse#17](https://github.com/cao772/muse/issues/17)、[CAO#35](https://github.com/cao772/cao/issues/35)。
