# Multi-Agent Routing (OpenClaw Official Docs Mirror)

> Source: https://docs.openclaw.ai/concepts/multi-agent.md
> Mirrored: 2026-04-18

Goal: multiple *isolated* agents (separate workspace + `agentDir` + sessions), plus multiple channel accounts (e.g. two WhatsApps) in one running Gateway. Inbound is routed to an agent via bindings.

## What is "one agent"?

An **agent** is a fully scoped brain with its own:

* **Workspace** (files, AGENTS.md/SOUL.md/USER.md, local notes, persona rules).
* **State directory** (`agentDir`) for auth profiles, model registry, and per-agent config.
* **Session store** (chat history + routing state) under `~/.openclaw/agents/<agentId>/sessions`.

Auth profiles are **per-agent**. Each agent reads from its own:

```
~/.openclaw/agents/<agentId>/agent/auth-profiles.json
```

Main agent credentials are **not** shared automatically. Never reuse `agentDir` across agents (it causes auth/session collisions).

## Paths (quick map)

* Config: `~/.openclaw/openclaw.json` (or `OPENCLAW_CONFIG_PATH`)
* State dir: `~/.openclaw` (or `OPENCLAW_STATE_DIR`)
* Workspace: `~/.openclaw/workspace` (or `~/.openclaw/workspace-<agentId>`)
* Agent dir: `~/.openclaw/agents/<agentId>/agent` (or `agents.list[].agentDir`)
* Sessions: `~/.openclaw/agents/<agentId>/sessions`

## Routing rules (how messages pick an agent)

Bindings are **deterministic** and **most-specific wins**:

1. `peer` match (exact DM/group/channel id)
2. `parentPeer` match (thread inheritance)
3. `guildId + roles` (Discord role routing)
4. `guildId` (Discord)
5. `teamId` (Slack)
6. `accountId` match for a channel
7. channel-level match (`accountId: "*"`)
8. fallback to default agent (`agents.list[].default`, else first list entry, default: `main`)

## Concepts

* `agentId`: one "brain" (workspace, per-agent auth, per-agent session store).
* `accountId`: one channel account instance (e.g. WhatsApp account "personal" vs "biz").
* `binding`: routes inbound messages to an `agentId` by `(channel, accountId, peer)`.
* Direct chats collapse to `agent:<agentId>:<mainKey>`.

## Per-Agent Sandbox and Tool Configuration

Each agent can have its own sandbox and tool restrictions:

```json5
{
  agents: {
    list: [
      {
        id: "personal",
        workspace: "~/.openclaw/workspace-personal",
        sandbox: { mode: "off" },
      },
      {
        id: "family",
        workspace: "~/.openclaw/workspace-family",
        sandbox: { mode: "all", scope: "agent" },
        tools: {
          allow: ["read"],
          deny: ["exec", "write", "edit", "apply_patch"],
        },
      },
    ],
  },
}
```
