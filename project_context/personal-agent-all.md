# Personal Agent ALL：统一路由与能力总线

更新时间：2026-10-07。

当前分支 `feature/personal-agent-all` 基于 P1 HEAD `8d4113a`。Voice MVP 稳定基线仍为 `368df49`，Serena 与 Whisper 常驻、音量 80、Ready/Listening/Thinking/Speaking 状态机不改。

## 目标

Muse 只做实体入口，Mac/CAO 做能力编排：

```text
Muse
→ Whisper
→ Personal Agent Router
   ├ CAO Project OS
   ├ CAO → Superset → Codex
   ├ ChatGPT plan research
   ├ WeChat / CI / Open Loops / alerts
   ├ MCP / Dify / Computer
   └ Commerce / Life skills
→ Serena
```

设备不保存云密钥、ChatGPT OAuth token、Superset PSK、支付密码。

## 当前已接入的基础

### 统一 Router

路由优先级：

1. 明确 Codex 开发/反馈动作 → Codex capability。
2. 项目事实/阶段/下一步/风险 → CAO。
3. 购物/外卖语义 → Commerce capability。
4. 明确“用 GPT / 认真查 / 查网页 / 深度研究 / 看看我漏了什么” → ChatGPT plan。
5. ChatGPT 已授权且自动路由开启时，高难度问题按本地启发式评分进入 ChatGPT。
6. 其余继续走现有 DeepSeek / compatible provider。

路由判断只在本地执行，不为了决定“该用哪个模型”额外调用模型。

### Deep Reflection

用户确认的反思问题：

> 在我最近反复讨论的问题背后，有没有一个更深的问题，是我一直在绕着它走，却没有真正问出来的？

只有用户明确要求“还有什么没想到/更深问题/反思”等，或后续高价值反思策略触发时才附加；要求模型没有真正重要发现时不要硬凑。

### ChatGPT plan research

使用 OpenAI 官方 Sign in with ChatGPT 的 open-source / locally hosted flow：

- 首次使用 `client_id=dynamic_agent_client`。
- 回调仅监听 `127.0.0.1`。
- PKCE S256、state、nonce。
- ID token 用 OpenAI JWKS 做 RS256 签名、issuer、audience、expiry、nonce 校验。
- 必须取得 `chatgpt.tokens.use.direct` scope。
- access / refresh / ID token 只保存在 Mac 私有文件，0600；目录 0700。
- access token 过期前使用 rotating refresh token 更新；刷新串行化。
- Responses API 请求固定 `store=false`、`stream=true`。
- 模型从当前 ChatGPT 账号的 `/v1/models` 实时枚举；不硬编码某个模型一定存在。
- 网页研究使用 Responses `web_search`；默认 search context 为 low，可配置。
- 不读取 ChatGPT 历史聊天或 Memory。
- 默认关闭，需用户在浏览器明确授权。

本机授权命令：

```sh
uv run muse-chatgpt-signin
```

授权后在 `.env`：

```env
MUSE_CHATGPT_ENABLED=true
MUSE_CHATGPT_AUTO_ENABLED=true
MUSE_CHATGPT_CREDENTIALS_PATH=~/.config/muse/chatgpt-plan.json
MUSE_CHATGPT_MODEL=
MUSE_CHATGPT_WEB_CONTEXT=low
```

Plus 用量属于用户现有 ChatGPT plan，不是独立额度。不要在自动任务中无限重试。

## 未接通时的行为

Router 可以识别 Codex / Commerce 等动作，但在对应受控 adapter 尚未接通时会明确回答“还没接通”，不会让通用 LLM 假装已经执行。

ChatGPT 显式请求在未授权时不会偷偷退回 DeepSeek冒充 GPT；自动高难度路由在 ChatGPT 不可用时才允许保守回退普通模型。

## 下一步

CAO 分支 `codex/personal-agent-all` 承接：

- Codex 启动 / 进度 / model profile / reasoning / feedback / test result；
- Open Loops；
- Completion Judge；
- Attention / Quiet；
- 微信 / CI / Codex 统一提醒；
- project drift；
- 恢复现场与今日优先级；
- Commerce / Computer 的受控动作协议。

高风险动作继续需要确认；支付由本人完成。
