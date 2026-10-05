# 集成扩展

- `llm.py`：`TextProvider` 接口和 `MockProvider`。DeepSeek、Qwen、OpenAI-compatible 仅保留 provider 名称，尚无网络请求实现。
- `mcp.py`：`ToolAdapter` 接口，尚无 MCP 客户端或工具执行实现。
- GitHub、Dify：待具体用例确定后新增 adapter，不提前引入依赖。

Stage 0 不读取云服务密钥、不调用计费服务。新增真实 provider 时应同时增加超时、错误映射、配置校验与隔离网络的测试。
