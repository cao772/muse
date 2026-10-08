# Muse Personal Agent P2

基线P1 `8d4113a`，独立 `feature/p2-codex-control`。Muse只能通过CAO Personal Execution API启动/查询/反馈，不能直接操作Superset、Codex CLI或shell。Serena、音量80、常驻Whisper/TTS、USB音频校验及忙时录音禁用保持原实现。

启用需要 MUSE_CAO_ENABLED=true、MUSE_CAO_EXECUTION_ENABLED=true、MUSE_CAO_BASE_URL=本机CAO地址，及单独的MUSE_CAO_MUSE_TOKEN。CAO负责验证绑定、Host版本、受限preset与反馈保护补丁；凭据不会打印或上板。默认关闭执行能力，P1只读查询独立可用。

支持“让 Codex 修复测试项目”“当前用什么模型”“Codex现在做到哪了”“测试过了吗”“告诉Codex，只修UI”等。启动必须精确匹配动态CAO项目名或ID，且有唯一授权仓库；歧义只询问。已有活跃或unknown任务时不再启动；请求超时保留执行UUID供查询，不盲重放。没有执行上下文不会猜任务。普通聊天仍DeepSeek；项目查询仍P1。

fast/balanced/strong与low/medium/high由CAO解析实际模型。单独说“用强模型，高推理”设置下一项任务，当前会话不热切换。重启muse-talk后不自动选择历史任务；运行态上下文只存内存，不保存完整会话/语音。反馈正文不在Muse日志或Git保存，CAO只存元数据。

圆屏首页显示CODEX状态/profile；View status详情页展示短项目ID和Needs you。设备端只接受白名单状态、profile和最多24字节ASCII项目标识（现有字体没有中文字库），拒绝任意控制字符。Voice Ready和Codex Waiting是两种状态：远端工作时语音仍可Ready，以查询/反馈；本机录音→处理→播放期间Record继续禁用。Host租约过期显示Unknown/Host offline。

所有reply保持现有120字/分段TTS边界，执行状态每3秒只读轮询，不重复启动/反馈。poll错误显示unknown，不用DeepSeek编造执行结果。开发单元/静态检查完成后统一本机及实体板验收，实际结果见下节。

## 板端问题复核（2026-10-07）

首次三轮体验未验收通过：执行项目查询超过旧 P1 的 5 秒上限，无活跃任务的“当前用什么模型”又误入普通聊天。执行启动的动态项目读取改用 ExecutionClient 的 60 秒上限，不改 P1 查询配置；支持明确中文“开始开发”启动，模型问句在没有任务时明确答复，不编造模型。开发进度只读真实 latest_progress，总回复仍不超过 120 字。日志新增 intent / route_result 枚举，不保存转录文本。

恢复离线 Superset Host 后，旧本机会话仍是 Unknown，没有重放；已有 7 项真实通过的报告与独立 unittest 结果保留。新版板端验收等待用户重新启动一次专用语音测试任务，本节不提前标通过。

第二次板端启动实际创建 `fd432f08-be0f-4f9d-9bd2-345fa75dc07b`，balanced / gpt-6.1-sol / medium，状态日志 Starting → Running → Waiting，整轮 30.878 秒、按键到首音 24.725 秒。用户确认固定 5 秒录音在说完前结束；任务关键部分未收全，Agent 按测试仓库 README 做了 normalize_title（真实事件 7 passed / 0 failed），因此这次仍不算加法任务验收通过。

增加截断任务保护：只说项目、缺少具体操作时不启动，不借用 README 猜任务。`--execution-id UUID` 仅由本机操作者明确指定恢复查询/反馈上下文，通过 scoped API 检查授权，不启动或恢复 Codex harness、不自动选历史任务。启动 POST 正在等待结果时不并发查询其尚未完成的记录，避免屏幕短暂误显 Unknown。录音仍为固定 5 秒，本轮不扩展音频协议；使用短句启动，再以短句追加需求。当前等待板端反馈、模型与结果查询验收。

## 2026-10-07 晚间暂停交接

用户决定休眠/关机，明天继续。本轮代码已保存在两个独立 worktree，尚未提交、推送或创建 P2 Draft PR；正式分支和 P1/M9 历史未修改。

板端先前的短句反馈、模型查询、测试查询三轮已回 Ready，用户确认首页 CODEX 状态。反馈进入同一执行 fd432f08-be0f-4f9d-9bd2-345fa75dc07b；新增 addition.py 和八项加法测试，加上原七项标题测试，共 15 passed / 0 failed。独立 unittest 复验一致，测试仓库 HEAD 仍 fec4047，没有自动提交。该验收在固定 5 秒固件时完成。

随后用户要求等待连续安静 3 秒再处理；新固件已烧录，网络握手/三次 pong 复验通过，完整 140 项测试及 lint/format 通过。3 秒停顿的板端时机尚未收到用户确认，不能标实机通过。详情见 adaptive-recording.md。

降温时关闭了本轮 Next.js 开发 API 与 Whisper/Serena Voice 服务；CPU 空闲率实测由约 45% 升至 85%，可用内存约 4.6GB。本轮结束检查未发现 muse-talk、模型 worker 或轻量测试接收器仍运行。不自动恢复或重放任务。

续接：先确认 USB/设备供电；断电后需重新下发主仓库忽略的 .env.device（不打印）。先用不加载模型的接收器验证 >5秒说话、短暂停顿继续、连续3秒安静结束，再视温度恢复服务。Superset Host 和开发 API 当前需重新核验，不沿用旧 manifest/会话在线状态；若恢复 Muse 上下文，只显式 inspect 已授权 UUID，不启动/恢复 Codex harness。最后补验剩余 P2 安全分支、更新两边文档、提交两边子分支并创建两个 Draft PR、附加到此任务、核对 CI；不合并正式分支、不写 Notion。

Muse worktree: /Users/caoyh/.codex/worktrees/muse-p2-control/muse (feature/p2-codex-control)
CAO worktree: /Users/caoyh/.codex/worktrees/cao-p2/cao (codex/muse-codex-control)

## 2026-10-08 ALL 整合与网络恢复

保留 P2 子分支，整合 Muse ALL bc1af1c 与 CAO ALL 4e08796，不修改 main/cao 或父分支。原执行路由改名 integrations/execution_agent.py，与 ALL 的 personal_agent.py 分离；明确执行意图先进入受控 P2，普通请求完整交给 ALL 的 PersonalAgentProvider，保留 GPT 研究路由及 CAO 项目事实边界。新增回归证明长期风险/架构问题继续走 GPT，普通聊天保持原超时。继续执行只向活跃已绑定会话追加反馈；当前 reasoning/profile/model 查询显示实际受控解析结果，无上下文不猜。

实测 HYETEC_705_5G 在 45 秒内未获取 IP。切换手机热点后 Mac 与板子连通，重新下发本地忽略配置；Wi-Fi、鉴权 WebSocket、hello、三次 pong 全通过。未将热点凭据或 device token 写入文档。CAO Personal API 返回唯一授权测试仓库及三档 profile，Host 已恢复。

整合后验证 Muse 150 passed，Ruff / format；CAO 334 passed，前端 40 passed。尚未完成本轮新版 3 秒停顿及整合后的语音控制实机验收，不把旧固定 5 秒验收冒充新版结果。


## 2026-10-08 整合后本机执行验收

Muse PR #3 (`bc1af1c`) 与 CAO PR #30 (`4e08796`) 已整合到两个 P2 子分支；没有合并正式分支。P2 Draft PR 为 Muse #5 / CAO #31。整合后的 Gateway、firmware 及 CAO CI 已全部通过：Muse 150 项、CAO 334 项 Python / 40 项前端测试。

通过实际 Muse 执行路由启动专用测试仓库任务 `5dc29cbe-f19c-453a-811b-638d7bcd75cf`，解析模型为 fast / gpt-6-luna / low。启动响应 4.611 秒，模型与推理查询约 0.02 秒；启动后首次查询仍可能暂时 Unknown，随后真实报告转为 Waiting。新增减法函数与 4 项测试；同一会话追加整数类型约束后 6 项通过；继续执行并补边界后 9 项通过。测试查询返回实际 9 passed / 0 failed；独立 `python3 -m unittest -v` 复验一致，测试仓库 HEAD 仍 `fec4047`，只有两个未跟踪实现/测试文件，没有自动 Git 提交。Waiting 表示等待下一步，formal_completion 仍 false。

本次 Superset Host 离线原因是开发版监听启动父进程：临时启动命令结束后 Host 自动退出。现以独立常驻父进程等待 Electron 子进程结束，保留原开发数据目录与受控补丁；没有修改上游退出策略，也没有重新启动先前高占用的开发 API。Gateway / Voice 以独立会话启动，日志只在本机临时目录。Mac 睡眠、断电或退出这些服务后，仍需重新核验 Host 与设备 RAM 配置，不自动重放任务。

3 秒连续静音录音已实测 13.2 秒 / 844800 字节，USB 完整校验并回 Ready；用户随后确认“这个没问题”。该轻量接收验证没有加载模型或执行开发任务。整合后的新版板端语音开发闭环正在统一验收，未提前标为通过。
