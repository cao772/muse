# Personal Agent P1：Muse → CAO 项目查询

2026-10-07。基线为 Voice MVP 稳定提交 `368df49`。本阶段只建立 Muse 到 CAO Project OS 的只读桥，不接 Codex 执行、不改项目、不 push / merge / deploy。

## 目标

把实体 Muse 从“语音聊天终端”升级为“个人项目操作系统的语音入口”：

```text
Muse 语音
→ Whisper
→ Project Query Router
→ CAO Central API
→ 项目 brief
→ Serena
→ 扬声器
```

普通聊天仍走 DeepSeek / compatible provider。

## 边界

- 仅允许 CAO base URL 为 loopback HTTP：`127.0.0.1` / `localhost` / `::1`。
- P1 只调用现有 GET：
  - `/api/v1/projects`
  - `/api/v1/projects/{project_id}/brief`
- 不需要、也不读取 `COLLECTOR_TOKEN`。
- 不访问 CAO 写接口，不新增网络监听，不把 CAO 暴露到局域网。
- 项目问题命中 CAO 后，CAO 故障时明确报不可用，不能退回 LLM 猜项目事实。
- 日志只增加 `answer_source=cao|llm` 元数据，不打印项目 brief 全文或用户转录。

## 第一阶段语音

- “我现在有哪些项目？”
- “法规知识库项目现在进展怎么样？”
- “法规知识库项目下一步是什么？”
- “法规知识库项目现在有什么风险？”

匹配依赖 CAO 实时项目列表；不把项目名硬编码进 Muse。当前仅对明显的项目/进展/下一步/风险/阻塞等问法进入项目路由，其他语音继续走通用模型。

## 配置

```env
MUSE_CAO_ENABLED=true
MUSE_CAO_BASE_URL=http://127.0.0.1:8080
MUSE_CAO_TIMEOUT_SECONDS=5
```

默认关闭，保证原 Voice MVP 行为不变。

## P1 验收

1. 原 Voice MVP / Serena / 音量 80 / USB / 状态联动不退化。
2. CAO 开启时，项目列表和项目 brief 从真实本机 CAO 返回。
3. 项目查询结果可由 Serena 正常播报，单句仍受 120 字符边界约束。
4. CAO 停止后，项目查询明确提示“项目中枢暂时不可用”，不让 DeepSeek根据旧上下文猜测。
5. 普通问答继续走现有 LLM。
6. 全量 pytest / Ruff / Gateway / firmware CI 通过。

## 后续，不属于 P1

- “继续昨天那个”与 active project 上下文。
- CAO → Superset → Codex 执行。
- Codex 进度 / 审批 / 取消显示。
- MCP / GitHub / Dify 工具调用。
- 主动通知与定时任务。
