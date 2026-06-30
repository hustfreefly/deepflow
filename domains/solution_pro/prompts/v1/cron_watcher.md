---
id: solution/cron_watcher
version: "2.0.0"
component: solution
updated: "2026-06-24"
deprecated: true
replacement: "contracts/shared/watcher_config.py WRAPPER_PROMPT_TEMPLATE"
---

# ⚠️ DEPRECATED — 此文件已废弃

**替代方案**: 使用 `contracts/shared/watcher_config.py` 中的 `render_wrapper_prompt()` 函数。

主 Agent 创建 watcher cron job 时，应使用：

```python
from contracts.shared.watcher_config import render_wrapper_prompt, DeliveryConfig

# 1. 渲染 wrapper prompt
wrapper_prompt = render_wrapper_prompt(
    config_path=f"{deepflow_root}/domains/solution_pro/config/watcher_config.json",
    base_path=base_path,
    run_start_at=run_start_at,
    cron_job_id="{cron_job_id}",  # placeholder，创建后回填
    deepflow_root=deepflow_root,
)

# 2. 验证 delivery 配置
delivery = DeliveryConfig(mode="announce")  # 不指定 channel/to，使用当前会话 channel
delivery_dict = delivery.to_cron_dict()

# 3. 创建 cron job
cron(action="add", job={
    "name": f"deepflow_watcher_{session_id[:8]}",
    "schedule": {"kind": "every", "everyMs": 180000},
    "sessionTarget": "isolated",
    "payload": {
        "kind": "agentTurn",
        "message": wrapper_prompt,
        "timeoutSeconds": 60,
        "lightContext": True
    },
    "delivery": delivery_dict,
    "enabled": True
})
```

**禁止**：
- ❌ 使用此文件中的 prompt 创建 watcher
- ❌ 在 wrapper prompt 中让 LLM 调用 message tool
- ❌ 硬编码 feishu open_id 到 delivery.to
