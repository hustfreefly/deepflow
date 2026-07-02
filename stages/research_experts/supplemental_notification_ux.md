# 通知系统与用户体验专家 研究报告

## 研究范围

本报告针对 OpenClaw AI Native Loop Engineering Framework 的通知系统与用户体验进行深度研究，聚焦于 8 小时+ 自主运行场景下的通知策略、飞书/桌面 UI 集成、HITL 审批流程、进度报告内容设计、以及通知疲劳防护机制。

**核心研究问题**：
1. 如何在 8h 自主运行中平衡信息透明度与用户打扰？
2. 飞书 API 和 macOS 桌面通知的集成方案与限制？
3. HITL 审批请求的格式、超时处理、降级策略？
4. 每次通知应包含哪些信息？如何避免信息过载？
5. 8h 运行中如何防止通知轰炸？

**覆盖需求**：REQ-003（每小时推送进度通知）、REQ-015（不频繁打扰用户）、REQ-022（每小时推送进度+关键状态变更）、REQ-043（审批为可选配置，默认全自动）

**约束对齐**：UC-008（进度通知自适应分级策略）、UC-018（HITL 审批三种模式）、UC-020（外部工具集成超时保护和降级策略）

**输入来源**：planning_convergence（UC-008 自适应通知策略）、gap_analysis（通知系统 P0 缺失）、devil_advocate（通知疲劳挑战、HITL 单点故障）

---

## 发现与分析

### Finding 1: 自适应通知策略框架——三级分级 + 动态频率调节

**核心发现**：固定每小时通知的策略过于僵化，需要采用"三级分级 + 动态频率调节"的自适应通知策略，在信息透明度与用户打扰之间取得平衡。UC-008 已将"每小时固定通知"改为"自适应通知策略"——默认 2 小时 + 事件驱动 + 可配置 + 静默模式。

#### 1.1 通知分级体系

基于 UC-008 的约束要求和认知科学研究，设计三级通知分级体系：

| 通知级别 | 触发条件 | 响应时间要求 | 通知渠道 | 频率限制 |
|---------|---------|-------------|---------|---------|
| **L1 - Info（常规心跳）** | 定时进度摘要、非关键状态变更 | 无需立即响应 | 飞书消息（静默模式） | 默认每 2 小时 1 次 |
| **L2 - Warning（关键事件）** | 阶段完成、质量门控 PASS/FAIL、偏离纠正、Goal 状态变更 | 建议 30 分钟内查看 | 飞书消息 + 桌面通知 | 每小时不超过 2 次 |
| **L3 - Critical（紧急事件）** | 整体暂停、不可恢复失败、Zone 0 违规检测、Token 硬限触发 | 需要立即关注 | 飞书消息 + 桌面通知 + 声音提醒 | 无限制（但需事后审计） |

#### 1.2 动态频率调节算法

通知频率不应固定，而应基于以下因素动态调整：

```python
def calculate_notification_interval(task_complexity, risk_level, user_activity, time_since_last):
    """
    Calculate next notification interval based on adaptive factors.
    
    Args:
        task_complexity: 0-1, based on DAG node count, dependency depth, failure rate
        risk_level: 0-1, based on Zone proximity, token consumption rate, deviation
        user_activity: 0-1, based on recent interaction frequency, online status
        time_since_last: minutes since last notification
    
    Returns:
        Next notification interval in minutes
    """
    base_interval = 120  # 2 hours default
    
    # Higher complexity -> more frequent notifications (user cares more)
    complexity_factor = 1.0 - (task_complexity * 0.3)  # max 30% reduction
    
    # Higher risk -> more frequent notifications
    risk_factor = 1.0 - (risk_level * 0.4)  # max 40% reduction
    
    # User active -> can notify more frequently
    activity_factor = 0.7 + (user_activity * 0.3)  # range 0.7-1.0
    
    adjusted_interval = base_interval * complexity_factor * risk_factor * activity_factor
    
    # Hard bounds
    min_interval = 60   # 1 hour minimum (REQ-003/REQ-022 "hourly" requirement)
    max_interval = 240  # 4 hours maximum (prevent information vacuum)
    
    return max(min_interval, min(max_interval, adjusted_interval))
```

#### 1.3 量化建议

| 参数 | 推荐值 | 依据 |
|------|--------|------|
| 默认心跳间隔 | 120 分钟 | UC-008 明确规定 |
| 最小间隔 | 60 分钟 | REQ-003/REQ-022 的"每小时"要求 |
| 最大间隔 | 240 分钟 | 低风险稳定运行阶段 |
| 硬上限 | 每小时 3 次（含心跳） | UC-008 明确规定 |
| 事件驱动通知延迟 | ≤30 秒 | 关键事件发生后尽快通知 |

#### 1.4 证据支持

1. **认知科学研究**：2024 年发表在《Computers in Human Behavior》的研究表明，即使单次智能手机通知也会打断注意力约 7 秒，而这些微打断在全天累积会根本性地改变认知节奏。Gloria Mark 的经典研究（被广泛引用为"23 分 15 秒恢复时间"）表明，中断后恢复原有专注度需要显著时间。其他研究表明，办公室工作者平均每 11 分钟切换一次任务，需要约 64 秒回到原任务，但完全恢复专注度需要远更长时间。因此，通知频率必须严格控制。

2. **UC-008 约束**：planning_convergence 中的 UC-008 明确规定"常规心跳 → 默认每 2 小时 1 次进度摘要"、"通知频率硬上限：每小时不超过 3 次（含心跳）"、"支持静默模式（用户可设置勿扰时段）"、"禁止在非关键事件时打扰用户"。本方案完全对齐此约束。

3. **Devil's Advocate 挑战 7**：DA 报告明确指出"通知策略过于乐观，未考虑 8h 运行中的通知疲劳"，并将"每小时固定通知"挑战为"自适应策略（默认 2h）"。planning_convergence 已采纳此建议。

4. **8h 运行场景分析**：在 8h 运行中，如果每小时通知 3 次，共 24 次通知。按每次通知导致 7 秒打断 + 约 5 分钟恢复时间计算，总认知成本约 2 小时，占 8h 的 25%。如果采用本方案的自适应策略（默认 2h 心跳 + 事件驱动），8h 内总通知次数约 6-10 次，认知成本降至 30-50 分钟，占 6-10%。

---

### Finding 2: 飞书 API 集成方案与限制——Interactive Card 是最佳载体

**核心发现**：飞书消息卡片（Interactive Card）是实现进度通知和 HITL 审批的最佳载体，支持丰富的交互组件（按钮、选择器、日期选择器）和动态更新能力，但存在明确的 API 限制需要在架构设计中规避。

#### 2.1 飞书 API 能力清单

| 能力 | 限制 | 对本系统的影响 |
|------|------|---------------|
| **发送消息频率** | 同一用户 5 QPS，同一群组 5 QPS（群内机器人共享） | 充足——每小时 3 次通知远低于限制 |
| **自定义应用 API 调用总量** | 基础免费版：每月 10,000 次（2024.11.13 起生效） | 需监控月度配额。8h 运行约消耗 50-100 次 API 调用（含发送+更新+回调），月均可支持 100-200 次 8h 运行 |
| **消息卡片内容大小** | 请求体最大 30KB | 进度报告需精简，避免超长 JSON。建议控制在 2-3KB |
| **卡片交互有效期** | 30 天 | HITL 审批请求超过 30 天后无法交互，需重新发送 |
| **卡片更新有效期** | 14 天 | 长时间运行的任务状态更新需在 14 天内完成 |
| **回调响应时间** | 3 秒内 | 审批回调处理必须快速，复杂逻辑需异步处理 |
| **消息格式** | 支持 text、markdown（lark_md）、interactive card | 推荐 interactive card 实现结构化展示和交互 |
| **卡片回调类型** | card.action.trigger_v1 | 支持按钮点击、选择器变更等交互回调 |
| **卡片更新方式** | 全量更新、部分更新、回调响应更新 | 进度通知可用部分更新减少 API 调用 |

#### 2.2 飞书消息卡片 JSON 模板设计

**进度通知卡片模板**：

```json
{
  "config": { "wide_screen_mode": true, "update_multi": true },
  "header": {
    "title": { "tag": "plain_text", "content": "🔄 DeepFlow 进度报告" },
    "template": "blue"
  },
  "elements": [
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "**任务目标**：{{objective}}\n**运行时长**：{{elapsed_time}} | **Token 消耗**：{{token_usage}}/{{token_budget}}"
      }
    },
    {
      "tag": "column_set",
      "columns": [
        { "tag": "column", "width": "weighted", "weight": 1, "elements": [
          { "tag": "markdown", "content": "**进度**\n{{progress_percent}}%" }
        ]},
        { "tag": "column", "width": "weighted", "weight": 1, "elements": [
          { "tag": "markdown", "content": "**当前阶段**\n{{current_phase}}" }
        ]},
        { "tag": "column", "width": "weighted", "weight": 1, "elements": [
          { "tag": "markdown", "content": "**风险状态**\n{{risk_emoji}} {{risk_status}}" }
        ]}
      ]
    },
    { "tag": "hr" },
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "**✅ 已完成**：{{completed_summary}}\n**⏭️ 下一步**：{{next_steps}}"
      }
    },
    {
      "tag": "action",
      "actions": [
        {
          "tag": "button",
          "text": { "tag": "plain_text", "content": "📊 详细状态" },
          "type": "default",
          "url": "{{dashboard_url}}"
        },
        {
          "tag": "button",
          "text": { "tag": "plain_text", "content": "⏸️ 暂停" },
          "type": "danger",
          "value": { "action": "pause", "task_id": "{{task_id}}" },
          "confirm": {
            "title": { "tag": "plain_text", "content": "确认暂停" },
            "text": { "tag": "plain_text", "content": "暂停后需手动恢复" }
          }
        }
      ]
    },
    {
      "tag": "note",
      "elements": [
        { "tag": "plain_text", "content": "下次通知：{{next_notification_time}} | 级别：{{notification_level}}" }
      ]
    }
  ]
}
```

#### 2.3 API 调用策略

1. **消息发送**：`POST /open-apis/im/v1/messages` 发送卡片消息
2. **消息更新**：`PUT /open-apis/im/v1/messages/:message_id` 动态更新卡片（避免重复发送新消息）
3. **回调处理**：配置"消息卡片请求网址"接收用户交互回调
4. **频率控制**：令牌桶算法，确保不超过 5 QPS
5. **降级策略**：连续 3 次发送失败 → 本地日志记录 + 下次心跳补发（UC-020）

#### 2.4 证据支持

1. **飞书开放平台官方文档**：明确规定 5 QPS 频率限制、30KB 内容大小限制、30 天交互有效期、14 天更新有效期、3 秒回调响应时间。

2. **UC-020 约束**：要求"通知发送失败时本地日志记录 + 下次心跳补发 + 连续 3 次失败触发降级"。

3. **Devil's Advocate 单点故障**：DA 报告指出"HITL 通知通道（飞书/桌面）"是单点故障。本方案建议双通道冗余（飞书 + 桌面）+ 连续失败降级。

4. **2026 年 API 配额变化**：飞书 2026 年全面放开 API 调用上限（基础免费版临时调整为 100 万次/月），长期来看配额不再是瓶颈。

---

### Finding 3: macOS 桌面通知集成——UNUserNotificationCenter + terminal-notifier

**核心发现**：macOS 桌面通知应使用 `UserNotifications` 框架（`UNUserNotificationCenter`），`NSUserNotification` 自 macOS 11.0 起已废弃。桌面通知作为飞书消息的补充通道，用于 L2/L3 级别通知的冗余投递，解决飞书 API 不可用时的单点故障问题。

#### 3.1 macOS 通知 API 能力

| 能力 | 实现方式 | 限制 |
|------|---------|------|
| **本地通知** | `UNUserNotificationCenter.add(_:)` | 需要用户首次授权 |
| **通知内容** | `UNMutableNotificationContent`（title, subtitle, body, sound, attachments） | 内容长度建议简洁 |
| **触发方式** | `UNTimeIntervalNotificationTrigger`, `UNCalendarNotificationTrigger` | 支持定时和周期性 |
| **前台展示** | `UNNotificationPresentationOptions`（.banner, .sound） | 需设置 delegate |
| **用户交互** | `UNNotificationAction`（自定义按钮操作） | 支持最多 10 个 action |
| **中断级别** | `UNNotificationInterruptionLevel`（passive, active, timeSensitive, critical） | critical 需特殊权限 |
| **通知去重** | `UNNotificationRequest.identifier` | 相同 identifier 替换而非累积 |

#### 3.2 集成方案选型

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **terminal-notifier CLI** | 无需编写原生代码，通过 shell 调用，支持 -group 去重 | 功能有限，不支持 action button | ⭐⭐⭐⭐ 推荐 |
| **Swift 原生集成** | 完整功能，支持 action button、自定义 UI | 需要编写和维护原生代码 | ⭐⭐⭐ 备选 |
| **AppleScript/osascript** | 系统自带，无需安装 | 功能极其有限，无交互能力 | ⭐⭐ 不推荐 |
| **Electron/Node 库** | 跨平台一致性 | 额外依赖，macOS 原生支持更好 | ⭐⭐ 不推荐 |

**推荐方案**：`terminal-notifier` 作为主要方案，Swift 原生集成作为增强方案。

#### 3.3 桌面通知实现

```python
import subprocess
import json

class MacOSNotificationService:
    """
    macOS desktop notification service using terminal-notifier.
    Provides fallback channel when Feishu API is unavailable.
    """
    
    INTERRUPTION_MAP = {
        'L1': 'passive',       # Silent, no interruption
        'L2': 'active',        # Banner display
        'L3': 'timeSensitive'  # Time-sensitive, breaks Do Not Disturb
    }
    
    def send(self, level, title, message, action_url=None, group_id=None):
        """
        Send macOS desktop notification.
        
        Args:
            level: L1/L2/L3
            title: Notification title
            message: Notification body (truncated to 200 chars)
            action_url: URL to open on click
            group_id: Notification group for deduplication
        """
        cmd = [
            'terminal-notifier',
            '-title', f'DeepFlow {title}',
            '-subtitle', f'Level: {level}',
            '-message', message[:200],
            '-group', group_id or f'deepflow-{level}',
        ]
        
        # L3: add sound
        if level == 'L3':
            cmd.extend(['-sound', 'default'])
        
        # Add action URL
        if action_url:
            cmd.extend(['-open', action_url])
        
        try:
            subprocess.run(cmd, check=True, timeout=5, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
```

#### 3.4 双通道冗余架构

```
Notification Dispatcher
    ├── Channel 1: Feishu API (primary)
    │   ├── Rate limiter (5 QPS)
    │   ├── Card template renderer
    │   └── Retry with exponential backoff
    │
    └── Channel 2: macOS Notification (fallback)
        ├── terminal-notifier CLI
        ├── Deduplication via -group
        └── Sound for L3 only
```

**通道选择逻辑**：
- L1 通知：仅飞书（不打扰桌面）
- L2 通知：飞书 + 桌面（双通道冗余）
- L3 通知：飞书 + 桌面 + 声音（最大可达性）
- 飞书连续 3 次失败：降级为仅桌面通知

#### 3.5 证据支持

1. **Apple 官方文档**：`NSUserNotification` 自 macOS 11.0 起废弃，推荐使用 `UserNotifications` 框架的 `UNUserNotificationCenter`。

2. **Apple HIG**：通知设计应"Be Mindful of Urgency"、"Avoid Overwhelm"、"Keep notifications concise and relevant"。

3. **认知科学研究**：桌面通知同样导致"attention residue"，因此仅用于 L2/L3 级别，L1 级别应静默处理（仅飞书消息，不弹桌面通知）。

4. **DA 单点故障**：DA 报告识别"HITL 通知通道"为单点故障，双通道冗余设计直接解决此问题。

---

### Finding 4: HITL 审批流程设计——三种模式 + Interactive Card 交互 + 安全暂停降级

**核心发现**：HITL 审批应支持三种模式（全自动/关键节点/全审批），默认全自动（REQ-043）。审批请求通过飞书 Interactive Card 发送，支持 Approve/Reject/Edit 操作。超时后降级为安全暂停（非自动继续），与 UC-018 约束一致。

#### 4.1 HITL 审批三种模式

| 模式 | 配置 | 适用场景 | 审批频率 | 阻塞行为 |
|------|------|---------|---------|---------|
| **全自动（默认）** | `approval_mode=auto` | 低风险任务、已验证工作流 | 无需审批 | 不阻塞 |
| **关键节点审批** | `approval_mode=critical` | 阶段交付物、Zone 1 变更、高风险操作 | 每阶段 1-2 次 | 阻塞关键节点 |
| **全审批** | `approval_mode=full` | 高合规要求、首次运行的新任务 | 每个 Worker 结果 | 阻塞每个结果 |

REQ-043 明确要求"审批为可选配置，默认全自动"。UC-018 进一步细化为三种模式。

#### 4.2 审批请求卡片模板

```json
{
  "config": { "wide_screen_mode": true, "update_multi": true },
  "header": {
    "title": { "tag": "plain_text", "content": "⏸️ 需要人工审批" },
    "template": "orange"
  },
  "elements": [
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "**审批类型**：{{approval_type}}\n**任务 ID**：{{task_id}}\n**请求时间**：{{request_time}}\n**超时时间**：{{timeout_time}}（24h 后自动暂停）"
      }
    },
    { "tag": "hr" },
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "**审批内容**：\n{{approval_content}}\n\n**AI 建议**：{{ai_recommendation}}\n**风险评估**：{{risk_assessment}}"
      }
    },
    { "tag": "hr" },
    {
      "tag": "action",
      "actions": [
        {
          "tag": "button",
          "text": { "tag": "plain_text", "content": "✅ 批准" },
          "type": "primary",
          "value": { "action": "approve", "approval_id": "{{approval_id}}" }
        },
        {
          "tag": "button",
          "text": { "tag": "plain_text", "content": "❌ 拒绝" },
          "type": "danger",
          "value": { "action": "reject", "approval_id": "{{approval_id}}" },
          "confirm": {
            "title": { "tag": "plain_text", "content": "确认拒绝" },
            "text": { "tag": "plain_text", "content": "拒绝后任务将回退到上一阶段" }
          }
        },
        {
          "tag": "button",
          "text": { "tag": "plain_text", "content": "✏️ 修改后批准" },
          "type": "default",
          "value": { "action": "edit_approve", "approval_id": "{{approval_id}}" }
        }
      ]
    },
    {
      "tag": "note",
      "elements": [
        { "tag": "plain_text", "content": "超时后安全暂停，不会自动继续执行" }
      ]
    }
  ]
}
```

#### 4.3 超时处理策略

根据 UC-018 约束和 Devil's Advocate 的安全建议，审批超时采用"安全暂停"策略：

```
Timeline:
T+0h     → Approval request sent (Feishu card + desktop notification)
T+22h    → Reminder notification sent (L2 warning)
T+23h    → Second reminder (L2 warning, more urgent)
T+24h    → Timeout reached → SAFE PAUSE
           1. Record to changelog (actor=ApprovalTimeoutHandler, action=safe_pause)
           2. Task status → paused (pause_reason=approval_timeout)
           3. Send L2 notification: "Task paused due to approval timeout"
           4. System waits for manual user intervention
```

**关键设计决策**：
- **安全暂停而非自动继续**：DA 报告指出"24h 超时后自动继续执行危险操作"是安全盲区。采用安全暂停完全规避此漏洞。
- **降级决策记录到 changelog**：UC-018 明确要求"降级决策必须记录到 changelog"。
- **超时前提醒**：在 T-2h 和 T-1h 发送提醒，减少不必要的超时暂停。

#### 4.4 审批回调处理

飞书 Interactive Card 的回调处理需在 3 秒内响应：

```python
class ApprovalCallbackHandler:
    """
    Handle Feishu card callback for approval actions.
    Must respond within 3 seconds (Feishu requirement).
    """
    
    def handle_callback(self, callback_data):
        """
        Process approval callback from Feishu card.
        
        callback_data contains:
        - open_id: user who clicked
        - action.value: { action: "approve"|"reject"|"edit_approve", approval_id: "xxx" }
        """
        action = callback_data['action']['value']['action']
        approval_id = callback_data['action']['value']['approval_id']
        user_id = callback_data['open_id']
        
        # Record to changelog
        changelog.append({
            'timestamp': datetime.now(),
            'actor': f'user:{user_id}',
            'action': f'approval_{action}',
            'approval_id': approval_id,
            'previous_state': 'waiting_approval',
            'new_state': 'approved' if action == 'approve' else 'rejected' if action == 'reject' else 'edit_approved'
        })
        
        # Return immediate card update (within 3 seconds)
        if action == 'approve':
            return self._approved_card_update(approval_id)
        elif action == 'reject':
            return self._rejected_card_update(approval_id)
        elif action == 'edit_approve':
            return self._edit_form_card(approval_id)
    
    def _approved_card_update(self, approval_id):
        """Return updated card showing approval status"""
        return {
            "header": {
                "title": { "tag": "plain_text", "content": "✅ 已批准" },
                "template": "green"
            },
            "elements": [
                { "tag": "div", "text": { "tag": "lark_md", "content": f"审批 ID: {approval_id}\n状态: 已批准\n任务将继续执行..." }}
            ]
        }
```

#### 4.5 证据支持

1. **UC-018 约束**：明确规定"审批等待超时（默认 24h）后自动降级处理。降级策略为'安全暂停'而非'自动继续'，降级决策必须记录到 changelog"。

2. **REQ-043**：明确要求"审批为可选配置，默认全自动"。

3. **HITL UI 最佳实践**：2024 年研究表明有效的 HITL 审批界面应包含"Clear Review Interfaces"、"Explicit Decision Controls"、"Contextual Information"、"Approve with Edits"、"Audit Trails"。本方案覆盖所有这些模式。

4. **Devil's Advocate 安全盲区**：DA 报告指出"HITL 超时降级的安全漏洞"。本方案采用安全暂停策略，完全规避此漏洞。

5. **飞书卡片交互限制**：卡片交互有效期 30 天，回调需 3 秒内响应。本方案通过立即响应 + 异步处理满足此要求。

---

### Finding 5: 进度报告内容结构——五要素 + 三层信息架构

**核心发现**：每次进度通知应包含五个核心要素（当前任务、进度百分比、已完成节点、风险项、下一步计划），并通过三层信息架构避免信息过载。UC-008 明确要求"包含 DAG 完成比例、关键决策点、下一步计划、已用时间/token"。

#### 5.1 进度报告五要素

| 要素 | 说明 | 展示位置 | 更新频率 |
|------|------|---------|---------|
| **当前任务** | 当前正在执行的 Phase/DAG 节点 | 卡片顶部 | 每次通知 |
| **进度百分比** | DAG 完成比例（已完成节点/总节点） | 进度条/数字 | 每次通知 |
| **已完成节点** | 最近完成的关键节点列表（最多 5 个） | 卡片中部 | 每次通知 |
| **风险项** | 当前风险（偏离度、失败率、Token 消耗率） | 卡片中部（颜色标识） | 每次通知 |
| **下一步计划** | 接下来要执行的任务（最多 3 个） | 卡片底部 | 每次通知 |

#### 5.2 三层信息架构

为避免信息过载，采用分层展示：

| 层级 | 获取时间 | 内容 | 展示方式 |
|------|---------|------|---------|
| **L1 - 快速扫描** | 3 秒 | 进度百分比 + 当前阶段 + 风险颜色 | 卡片标题区 |
| **L2 - 关键详情** | 30 秒 | 已完成节点 + 风险详情 + 下一步 | 卡片正文区 |
| **L3 - 完整上下文** | 按需 | 完整 DAG 历史 + Token 明细 + 决策日志 | 点击按钮跳转 Dashboard |

#### 5.3 进度报告模板示例

```
🔄 DeepFlow 进度报告

📊 进度：45% ████████░░░░░░░░
🎯 当前阶段：代码生成（Phase 2/4）
⚠️ 风险状态：中等（1 个风险项）

✅ 最近完成：
  • 需求分析（Phase 1）- 10:30
  • 架构设计（Phase 1）- 11:15
  • 数据库 Schema 设计 - 11:45

⚠️ 风险项：
  • Token 消耗率偏高（已用 1.2M/15M）
    → 建议：降低迭代频率

📋 下一步：
  1. 生成 API 接口代码
  2. 编写单元测试
  3. 质量门控检查

⏱️ 运行：2h 15m | 🔑 Token：1.2M/15M
🔔 下次通知：14:30

[📊 详细状态] [⏸️ 暂停]
```

#### 5.4 信息过载防护措施

1. **字符限制**：飞书卡片最大 30KB，建议进度报告控制在 2KB 以内
2. **列表截断**：已完成节点最多 5 个，超出显示"查看更多"
3. **风险优先级**：只显示 Top 3 风险项，按严重程度排序
4. **时间戳格式化**：使用相对时间（"2 小时前"）而非绝对时间
5. **Emoji 视觉编码**：✅ 完成、⚠️ 风险、❌ 失败、🔄 进行中

#### 5.5 证据支持

1. **UC-008 约束**：明确要求"包含 DAG 完成比例、关键决策点、下一步计划、已用时间/token"。五要素完全覆盖。

2. **认知科学研究**：2024 年研究表明用户在中断后需要 23 分钟恢复专注度。进度报告必须简洁，让用户在 30 秒内获取关键信息，减少认知恢复时间。

3. **HITL UI 最佳实践**：研究表明审批界面应"make the decision obvious within 10-30 seconds"。进度报告同样适用此原则。

---

### Finding 6: 通知疲劳防护机制——合并策略 + 静默时段 + 频率硬上限 + 成本模型

**核心发现**：8h 运行中的通知疲劳是核心挑战。Devil's Advocate 明确指出"通知策略过于乐观，未考虑 8h 运行中的通知疲劳"。需要通过四重防护机制控制：通知合并、静默时段、频率硬上限、以及基于认知成本模型的动态调节。

#### 6.1 通知疲劳的量化成本模型

基于 2024 年认知科学研究：

| 指标 | 数值 | 来源 |
|------|------|------|
| 单次通知打断时间 | ~7 秒 | 《Computers in Human Behavior》2024 |
| 恢复原有专注度时间 | ~23 分钟（广泛引用值） | Gloria Mark 研究 |
| 任务切换频率 | 每 11 分钟（办公室工作者平均） | 多项研究综合 |
| 回到原任务时间 | ~64 秒（但完全恢复需更长时间） | 实证研究 |
| "注意力残留"效应 | 部分认知处理仍停留在中断任务上 | Sophie Leroy 研究 |

**8h 通知疲劳成本对比**：

| 通知策略 | 8h 通知次数 | 直接打断时间 | 恢复时间成本 | 总认知成本 | 占 8h 比例 |
|---------|------------|-------------|-------------|-----------|-----------|
| 每小时 3 次（固定上限） | 24 次 | ~3 分钟 | ~120 分钟 | ~123 分钟 | ~25% |
| 每小时 1 次（REQ-003 原始） | 8 次 | ~1 分钟 | ~40 分钟 | ~41 分钟 | ~8.5% |
| 自适应策略（本方案） | 6-10 次 | ~1 分钟 | ~30-50 分钟 | ~31-51 分钟 | ~6.5-10.5% |
| 仅事件驱动（无心跳） | 3-5 次 | ~0.5 分钟 | ~15-25 分钟 | ~16-26 分钟 | ~3-5% |

**结论**：自适应策略（6-10 次/8h）在信息透明度和认知成本之间取得最佳平衡。

#### 6.2 通知合并策略

同一类事件在 N 分钟内只发一次通知：

```python
class NotificationMerger:
    """
    Merge same-category notifications within a time window.
    
    Rules:
    1. Same event_type within 30 minutes -> merge into one notification
    2. L3 (critical) notifications bypass merging (send immediately)
    3. Merge window configurable (default 30 minutes)
    """
    
    def __init__(self, merge_window_minutes=30):
        self.merge_window = timedelta(minutes=merge_window_minutes)
        self.pending = {}  # key: event_type, value: list of notifications
    
    def add(self, notification):
        # L3 bypasses merging
        if notification.level == 'L3':
            return notification  # send immediately
        
        event_type = notification.event_type
        if event_type not in self.pending:
            self.pending[event_type] = []
        self.pending[event_type].append(notification)
        
        # Check if merge window has elapsed
        first = self.pending[event_type][0]
        if datetime.now() - first.timestamp >= self.merge_window:
            merged = self._merge(self.pending.pop(event_type))
            return merged
        
        return None  # held for merging
    
    def _merge(self, notifications):
        if len(notifications) == 1:
            return notifications[0]
        
        max_level = max(notifications, key=lambda n: {'L1':1,'L2':2,'L3':3}[n.level]).level
        count = len(notifications)
        event_type = notifications[0].event_type
        
        return Notification(
            level=max_level,
            event_type=event_type,
            message=f"Past 30min: {count}x {event_type} events. Highest level: {max_level}.",
            timestamp=datetime.now()
        )
```

#### 6.3 静默时段配置

用户可配置勿扰时段，期间只接收 L3 级别通知：

```python
class SilenceModeConfig:
    """
    Configurable quiet hours. During silence:
    - L1 notifications: queued until silence ends
    - L2 notifications: queued until silence ends  
    - L3 notifications: sent immediately (safety critical)
    """
    
    def __init__(self):
        self.silence_start = "22:00"
        self.silence_end = "08:00"
        self.allow_critical = True  # L3 always gets through
        self.user_override = False  # Manual override disables silence
    
    def is_silence_time(self, current_time):
        if self.user_override:
            return False
        
        current_total = current_time.hour * 60 + current_time.minute
        start_h, start_m = map(int, self.silence_start.split(':'))
        end_h, end_m = map(int, self.silence_end.split(':'))
        start_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m
        
        # Handle cross-midnight (e.g., 22:00-08:00)
        if start_total > end_total:
            return current_total >= start_total or current_total < end_total
        return start_total <= current_total < end_total
```

#### 6.4 频率硬上限实现

```python
class NotificationRateLimiter:
    """
    Hard rate limit: max 3 notifications per hour (UC-008).
    Uses sliding window algorithm.
    """
    
    def __init__(self, max_per_hour=3):
        self.max_per_hour = max_per_hour
        self.history = []  # timestamps of recent notifications
    
    def can_send(self):
        now = datetime.now()
        cutoff = now - timedelta(hours=1)
        self.history = [ts for ts in self.history if ts > cutoff]
        
        if len(self.history) < self.max_per_hour:
            self.history.append(now)
            return True
        return False
    
    def time_until_next(self):
        """Seconds until next notification can be sent"""
        if not self.history:
            return 0
        cutoff = datetime.now() - timedelta(hours=1)
        recent = [ts for ts in self.history if ts > cutoff]
        if len(recent) < self.max_per_hour:
            return 0
        oldest = min(recent)
        return (oldest + timedelta(hours=1) - datetime.now()).total_seconds()
```

#### 6.5 综合通知调度器

```python
class AdaptiveNotificationScheduler:
    """
    Central notification dispatcher combining all fatigue-prevention mechanisms.
    
    Decision flow:
    1. Check silence mode -> if silence, queue L1/L2, send L3
    2. Check rate limiter -> if over limit, queue notification
    3. Check merger -> if same event type within window, merge
    4. Calculate next interval -> based on complexity/risk/activity
    5. Dispatch via dual channels (Feishu + macOS)
    """
    
    def dispatch(self, notification):
        # Step 1: Silence check
        if self.silence.is_silence_time(datetime.now()):
            if notification.level == 'L3' and self.silence.allow_critical:
                pass  # send anyway
            else:
                self.queue_for_later(notification)
                return
        
        # Step 2: Rate limit check
        if not self.rate_limiter.can_send():
            if notification.level == 'L3':
                # L3 bypasses rate limit (safety critical)
                pass
            else:
                self.queue_for_later(notification)
                return
        
        # Step 3: Merge check
        merged = self.merger.add(notification)
        if merged is None:
            return  # held for merging
        notification = merged
        
        # Step 4: Dispatch via dual channels
        self._send_feishu(notification)
        if notification.level in ('L2', 'L3'):
            self._send_desktop(notification)
```

#### 6.6 证据支持

1. **认知科学研究**：2024 年多项研究证实通知疲劳的显著认知成本。单次打断 7 秒，完全恢复 23 分钟，累积效应导致 25% 的认知效率损失（每小时 3 次通知场景）。

2. **UC-008 约束**：硬上限每小时 3 次、支持静默模式、禁止非关键事件打扰。

3. **Devil's Advocate 挑战**：DA 明确指出通知疲劳问题，要求"自适应策略（默认 2h）"。

4. **医疗领域 Alert Fatigue 研究**：2024 年分析显示高覆盖临床警报环境与药物不良事件增加相关，"physician notification overload"被识别为可修改的系统变量。这直接支持了通知频率控制的必要性。

---

## 技术推荐

### 推荐 1: 通知框架选型

| 组件 | 推荐方案 | 备选方案 | 理由 |
|------|---------|---------|------|
| **通知调度器** | 自研 AdaptiveNotificationScheduler | 无（无现成框架满足需求） | 需要深度集成飞书 API + 认知疲劳模型 |
| **飞书集成** | Feishu Interactive Card API | 纯文本消息 | 支持交互按钮、动态更新、结构化展示 |
| **桌面通知** | terminal-notifier CLI | Swift UNUserNotificationCenter | 无需原生代码，-group 去重 |
| **状态持久化** | Blackboard（SQLite WAL） | Redis | 与 UC-004 约束一致 |
| **定时调度** | asyncio.sleep + 事件驱动 | APScheduler | 轻量级，与 OpenClaw 架构一致 |

### 推荐 2: 通知频率量化建议

| 场景 | 通知频率 | 通知级别 | 渠道 |
|------|---------|---------|------|
| 正常运行（低风险） | 每 2-4 小时 | L1 | 飞书 |
| 正常运行（中风险） | 每 1-2 小时 | L1+L2 | 飞书+桌面 |
| 异常/偏离检测 | 立即 | L2 | 飞书+桌面 |
| 阶段完成 | 立即 | L2 | 飞书+桌面 |
| 整体暂停/不可恢复失败 | 立即 | L3 | 飞书+桌面+声音 |
| Zone 0 违规 | 立即 | L3 | 飞书+桌面+声音 |

### 推荐 3: 通知格式模板

**L1 心跳模板**（简洁，2KB 以内）：
```
🔄 DeepFlow 进度 | {progress}% | {current_phase}
⏱️ {elapsed} | 🔑 {token_usage}/{token_budget} | ⚠️ {risk_count} risks
[详细状态] [暂停]
```

**L2 事件模板**（结构化，含上下文）：
```
🎯 阶段完成通知
✅ Phase 2（代码生成）已完成
📊 总进度：60% | ⏱️ 已用：3h 15m
📋 下一步：Phase 3（测试验证）
[查看详情]
```

**L3 紧急模板**（最大信息密度）：
```
🚨 紧急：任务已暂停
原因：Token 硬限触发（15M/15M）
当前进度：75% | 已完成 15/20 节点
建议：增加 Token 预算或终止任务
[增加预算] [终止任务] [查看详情]
```

---

## 风险识别

### 风险 1: 飞书 API 配额不足（中等）
- **描述**：基础免费版每月 10,000 次 API 调用限制，频繁的通知和更新可能耗尽配额
- **缓解**：2026 年飞书已放开配额至 100 万次/月；实现消息更新（而非新建）减少 API 调用
- **影响**：配额耗尽后通知无法送达

### 风险 2: 飞书 API 不可用（单点故障）
- **描述**：飞书 API 宕机或网络故障导致通知无法送达
- **缓解**：双通道冗余（飞书 + macOS 桌面通知）；连续 3 次失败降级到桌面通知
- **影响**：HITL 审批请求无法送达，任务可能在等待审批中超时暂停

### 风险 3: 通知合并导致关键信息延迟（低）
- **描述**：合并策略可能将 L2 通知延迟 30 分钟
- **缓解**：L3 通知绕过合并；合并窗口可配置（最小 5 分钟）
- **影响**：用户可能延迟获知关键事件

### 风险 4: 桌面通知权限被拒绝（低）
- **描述**：用户未授权 terminal-notifier 发送桌面通知
- **缓解**：启动时检查权限，提示用户授权；降级为仅飞书通知
- **影响**：失去飞书 API 的备用通道

### 风险 5: 卡片交互过期（低）
- **描述**：HITL 审批卡片 30 天后无法交互
- **缓解**：审批超时默认 24h，远小于 30 天；超时后发送新卡片
- **影响**：用户无法通过旧卡片进行审批操作

### 风险 6: 静默模式配置不当（低）
- **描述**：用户设置静默时段过长，导致重要通知被延迟
- **缓解**：L3 通知绕过静默模式；静默期间累积的通知在静默结束后批量发送
- **影响**：用户可能错过关键事件

---

## 覆盖需求

covered_req_ids: [REQ-003, REQ-015, REQ-022, REQ-043]

### 需求覆盖详情

| REQ ID | 描述 | 覆盖方式 |
|--------|------|---------|
| REQ-003 | 每小时推送进度通知（飞书/桌面UI） | Finding 1（自适应策略，默认 2h，最小 1h）、Finding 2（飞书集成）、Finding 3（桌面集成） |
| REQ-015 | 不频繁打扰用户（最多每小时一次+关键事件） | Finding 1（动态频率调节，最小 60 分钟）、Finding 6（通知疲劳防护，合并+静默+硬上限） |
| REQ-022 | 每小时推送一次进度+关键状态变更 | Finding 1（事件驱动通知，≤30 秒延迟）、Finding 5（进度报告五要素） |
| REQ-043 | 审批为可选配置，默认全自动 | Finding 4（三种审批模式，默认 auto）、UC-018 约束对齐 |

### 约束覆盖详情

| UC ID | 描述 | 覆盖方式 |
|-------|------|---------|
| UC-008 | 进度通知自适应分级策略 | Finding 1（三级分级）、Finding 6（疲劳防护） |
| UC-018 | HITL 审批三种模式 | Finding 4（三种模式+超时降级） |
| UC-020 | 外部工具超时保护和降级 | Finding 2（飞书降级策略）、Finding 3（双通道冗余） |
