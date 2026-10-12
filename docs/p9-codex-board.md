# P9 / P10｜Codex 多项目看板与确认反馈

基于 Muse P8 `ee0b6ba`，CAO 配套基于 `38733f9`。独立 Draft，不合并既有阶段。

## 已实现

- CAO `GET /api/v1/personal-agent/codex-board`：独立只读令牌、精确项目/仓库与设备 capability 过滤。只读取登记的工作区，不枚举 Host 全局工作区或私人目录；不调用会写入数据库的 P2 inspect。
- 最大 50 个项目、每项目 5 个会话，去重并按待确认/失败/运行排序。源覆盖未知仍为 `null`；登记项目数是本令牌可见的授权绑定数，不是整台 Mac 的项目总数。
- Host 只读观察分别绑定 terminal / harness。旧会话替换、断联、结束不冒充正在工作。真实事件按项目、task、execution UUID 精确关联；缺进展、文件、测试或时间即未知。
- Gateway 严格 DTO / 有界 USB 帧；第三页显示项目、任务、短进展、测试、事件年龄，支持上一/下一项目和下一任务。保留七页、微信、十一、农场与现有语音。
- P10 基础实现：选中任务后录入反馈，明确展示目标/指令，再用语音“确认发送”或圆屏确认。确认前刷新只读范围，再 inspect 当前执行绑定，最后复用 P2 feedback；未知结果禁止重放。仅 P2 受控会话可反馈；登记的其他会话始终只读。
- 非 Ready 禁用选择/确认。默认只读与控制开关均关闭；看板开启后禁用直接语音新建任务，避免沿用单任务路由猜目标。暂停、终止、新任务启动、自动合并/部署未开放。

## 本机接入边界

CAO 配置的 `bindings` 中，`board_enabled=true` 只授权读摘要，不会开通 P2 launch。原 `personal_enabled=true` 继续代表既有受控执行权限。建议显式指定 `display_alias` 与可信事件作者 `board_event_user_id`；未绑定事件作者时不显示事件正文/测试，文件名展示另需 `board_file_details_enabled=true`。

非 Muse 创建的 Host 会话必须人工登记 `codex_board_sessions`，明确 `id`（UUID）、project/repository、workspace、terminal、原 `agent_session_id`、provider_instance、当前 Muse capability，及可公开的 `display_title`。它不会因此取得反馈权。其他 Codex Desktop / CLI 来源尚未自动接入；不能将登记入口称为全机自动发现。

CAO 使用 `CAO_MUSE_BOARD_TOKEN`（至少32 ASCII字符），必须区别于 Muse 执行和采集令牌。令牌仅位于本机忽略配置。Mac 设置见 `.env.example` 的 `MUSE_CODEX_BOARD_*`；P10 控制只有 P9 真实只读验收通过后才开启。

## 中文与交互限制

设备字库为固定子集，包含固定 UI 和首批技术用词。未覆盖的动态摘要明确提示“详情请在Mac查看”，语音可读完整授权摘要，不输出乱码。反馈最长80字，必须能完整显示；确认页滚动显示全文，不发送被截断的长指令。新增项目别名需核对字库，而非无限引入字体/图集。当前为单项目卡片切换，未做多卡列表或文件 diff。

## 2026-10-12 验证证据

- Gateway 新增 50项目×5会话选择、跨项目消歧、撤权、敏感字段、超时不重放、确认只发送一次、最大 UTF-8 帧预算、字库一致性测试。
- CAO 新增独立读令牌、执行令牌隔离、项目仓库错配、替换 harness、离线、真实事件关联、文件权限、250会话去重与只读绑定测试。原 P2 API 测试继续执行。
- 实际 LVGL 主机编译/渲染并检查忙时禁用及 unavailable 页面。截图中的50项目、12项测试是模拟数据，不是本机实时数据。
- 本机独立只读服务绑定 `127.0.0.1:8092`，真实 CAO 数据卷只读挂载。复验当前可见登记项目1、有效观察项目0、未覆盖数未知；旧 Host manifest 已不存在，13条历史 execution 中不能重新绑定原 Host 的记录不会被当作实时任务。
- 没有新增项目授权，也没有烧录本轮固件。真实多项目、原会话反馈、10分钟板端交互及 USB 语音/存档回归仍待验收。P9 未通过实机前，P10 写开关保持关闭。

本地验证：Muse 218 项测试通过，Ruff/format/文档校验通过；固件 1788336 字节，app 剩余 308816 字节。内部 BSS/静态 RAM 仍通过64/96 KiB门禁。CI需以提交后的精确HEAD为准。
