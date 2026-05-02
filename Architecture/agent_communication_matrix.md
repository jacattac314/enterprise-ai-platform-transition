# Agent Communication Matrix
**Version:** 1.0 | **Last Updated:** 2025-05

This document defines every permitted communication path between agents in the multi-agent orchestration system. Communication not listed here is **blocked by default**.

---

## Communication Topology

```
External Input (Slack / Email / API)
         │
         ▼
   ┌─────────────┐
   │   INTAKE    │ ──── reads only, no write, no tool calls
   └──────┬──────┘
          │ AgentMessage (intent + entities)
          ▼
   ┌─────────────────┐
   │  ORCHESTRATOR   │ ◄──── only agent that can spawn others
   └────┬────────────┘
        │
        ├──────────────────────┐
        │                      │
        ▼                      ▼
 ┌─────────────┐       ┌───────────────┐
 │  RESEARCH   │       │   EXECUTION   │
 └──────┬──────┘       └───────┬───────┘
        │                      │
        │ context bundle        │ action result
        └──────────┬───────────┘
                   │
                   ▼
           ┌──────────────┐
           │  ESCALATION  │ ──── fires only on trigger conditions
           └──────────────┘
```

---

## Message Permission Matrix

| Sender | Recipient | Allowed? | Message Types | Notes |
|--------|-----------|----------|---------------|-------|
| INTAKE | ORCHESTRATOR | ✅ | `route` | Only valid output from INTAKE |
| INTAKE | RESEARCH | ❌ | — | Must go through ORCHESTRATOR |
| INTAKE | EXECUTION | ❌ | — | Must go through ORCHESTRATOR |
| INTAKE | ESCALATION | ❌ | — | Must go through ORCHESTRATOR |
| ORCHESTRATOR | INTAKE | ✅ | `clarify` | Request clarification re-parse |
| ORCHESTRATOR | RESEARCH | ✅ | `research` | Query with structured context |
| ORCHESTRATOR | EXECUTION | ✅ | `execute` | Action with full context bundle |
| ORCHESTRATOR | ESCALATION | ✅ | `escalate` | When escalation trigger fires |
| RESEARCH | ORCHESTRATOR | ✅ | `context_result` | Returns structured data bundle |
| RESEARCH | EXECUTION | ❌ | — | Cannot direct execution |
| RESEARCH | ESCALATION | ❌ | — | Cannot trigger escalation |
| EXECUTION | ORCHESTRATOR | ✅ | `action_result` | Success/failure + artifacts |
| EXECUTION | ESCALATION | ❌ | — | Must route through ORCHESTRATOR |
| ESCALATION | ORCHESTRATOR | ✅ | `human_response` | When human replies to escalation |
| ESCALATION | EXECUTION | ❌ | — | Cannot resume execution directly |

---

## Tool Access Per Agent

### INTAKE Agent
| Tool | Access | Reason |
|------|--------|--------|
| Slack read (trigger) | ✅ Read | Receives incoming messages |
| Email read (trigger) | ✅ Read | Receives incoming emails |
| All write tools | ❌ None | Intake is parse-only |
| All Jira/Notion tools | ❌ None | No research at intake layer |

### RESEARCH Agent
| Tool | Access | Reason |
|------|--------|--------|
| `jira_search` | ✅ Read | Query issues, sprints, projects |
| `notion_search` | ✅ Read | Query workspace content |
| `calendar_read` | ✅ Read | Check availability, past events |
| `slack_history_read` | ✅ Read | Context from recent messages |
| All write tools | ❌ None | Research never modifies state |

### EXECUTION Agent
| Tool | Access | Reason |
|------|--------|--------|
| `jira_create_issue` | ✅ Write | Create tickets from intake |
| `jira_update_issue` | ✅ Write | Update status, add comments |
| `notion_create_page` | ✅ Write | Create status updates, summaries |
| `notion_update_page` | ✅ Write | Update existing pages |
| `slack_post_message` | ✅ Write | Post to channels |
| `slack_send_dm` | ❌ None | Only ESCALATION may DM |
| `calendar_write` | ❌ None | Not in scope v1 |
| `jira_delete` | ❌ None | Destructive ops excluded |

### ESCALATION Agent
| Tool | Access | Reason |
|------|--------|--------|
| `slack_send_dm` | ✅ Write | Notify humans privately |
| `slack_post_message` | ✅ Write | Post escalation notices |
| All read tools | ✅ Read | Needs full context to package |
| `jira_create_issue` | ❌ None | Escalation doesn't execute |
| `notion_write` | ❌ None | Escalation doesn't write docs |

### ORCHESTRATOR Agent
| Tool | Access | Reason |
|------|--------|--------|
| All agent spawn | ✅ Full | Coordination role |
| All tools (indirect) | Via agents only | Does not invoke tools directly |

---

## Context Bundle Schema

When RESEARCH returns context to ORCHESTRATOR, it uses this schema:

```python
@dataclass
class ContextBundle:
    trace_id: str
    jira_results: list[dict]      # Matching issues/tickets
    notion_results: list[dict]    # Matching pages
    slack_context: list[dict]     # Relevant recent messages
    calendar_context: list[dict]  # Relevant events
    confidence: float             # 0.0–1.0: how complete is this context?
    gaps: list[str]               # What couldn't be found
    retrieved_at: str             # ISO-8601
```

When confidence < 0.60 or gaps is non-empty, ORCHESTRATOR must decide: attempt execution with partial context, or escalate for clarification.

---

## Inter-Agent Security Rules

1. **No direct agent-to-agent tool calls** — all tool invocations go through the tool registry enforcement layer
2. **No free-text agent communication** — all messages use `AgentMessage` envelope
3. **All messages are logged** — trace_id links every message in a chain
4. **TTL enforcement** — any message not acted on within `ttl_seconds` is expired and the task is escalated
5. **No agent can modify its own trust level** — trust is assigned at initialization, not runtime
6. **EXECUTION agent requires ORCHESTRATOR signature on every action** — execution message must carry `orchestrator_approval: true` flag

---

## Escalation Threshold Reference

| Condition | Check Location | Threshold | Action |
|-----------|---------------|-----------|--------|
| INTAKE confidence | INTAKE output | < 0.60 | Route to ESCALATION |
| RESEARCH completeness | ContextBundle.confidence | < 0.60 | ORCHESTRATOR decides |
| EXECUTION failure | action_result.status | 2 consecutive failures | ORCHESTRATOR → ESCALATION |
| Task TTL | AgentMessage.ttl_seconds | Exceeded | Auto-escalate |
| Sensitive keyword | INTAKE entity extraction | PII / legal / financial detected | Override to ESCALATION |
| Tool registry miss | Tool enforcement layer | Any unregistered call | Block + alert |

---

## Version History

| Version | Change | Date |
|---------|--------|------|
| 1.0 | Initial matrix | 2025-05 |
