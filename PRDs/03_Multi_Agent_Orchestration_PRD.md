# PRD 03: Multi-Agent Orchestration — Autonomous Task Loop (Notion / Slack / Jira)
**Version:** 1.0  
**Status:** Draft — Ready for Engineering Review  
**Owner:** AI Platform Team  
**Last Updated:** 2025-05

---

## 1. Problem Statement

Enterprise teams spend 20–40% of coordination time on work *about* work: routing tasks, summarizing status, updating tickets, and notifying stakeholders. These are high-frequency, low-complexity operations — the exact profile where autonomous agents create asymmetric ROI.

The current state is a patchwork of manual hand-offs:
- Engineers update Jira manually after Slack discussions
- PMs pull Notion docs to write status updates that mirror ticket data
- Standups rehash information that already exists in structured form

This PRD defines a **multi-agent orchestration layer** that closes these loops autonomously, escalating to humans only when resolution requires judgment.

---

## 2. Goals

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Reduce manual ticket updates by 70% | Measured via Jira audit log activity |
| G2 | Auto-generate weekly status summaries from live data | Zero-human drafts for routine status |
| G3 | Route incoming Slack requests to correct system in <30s | End-to-end latency on test suite |
| G4 | Human escalation rate < 15% of total agent task volume | Logged in task resolution table |

---

## 3. Non-Goals

- This system does NOT make approval decisions (budget, headcount, scope changes)
- Does NOT replace human judgment for risk assessment
- Does NOT write or merge code (separate CI agent spec)

---

## 4. Agent Architecture

### 4.1 Agent Roster

```
ORCHESTRATOR AGENT (Coordinator)
    ├── INTAKE AGENT         — Parses incoming requests (Slack, email, form)
    ├── RESEARCH AGENT       — Queries Notion, Jira, calendar for context
    ├── EXECUTION AGENT      — Writes to Jira, Notion, sends Slack messages
    └── ESCALATION AGENT     — Packages context for human hand-off
```

### 4.2 Agent Roles & Trust Levels

| Agent | Can Read | Can Write | Can Invoke | Trust Level |
|-------|----------|-----------|------------|-------------|
| ORCHESTRATOR | All systems | None | All agents | L3 — Full |
| INTAKE | Slack, email | None | ORCHESTRATOR | L1 — Read-only |
| RESEARCH | Jira, Notion, Calendar | None | None | L2 — Read + query |
| EXECUTION | Jira, Notion, Slack | Jira, Notion, Slack | None | L2 — Scoped write |
| ESCALATION | All (read) | Slack DM only | None | L2 — Notify only |

**Trust Level Definitions:**
- L1: Read-only. Cannot trigger downstream actions.
- L2: Scoped write. Can write to approved targets with logged actions.
- L3: Orchestration. Can spawn and direct other agents.

### 4.3 Communication Protocol

Agents communicate via a **structured message envelope**, not free-form text. This prevents prompt injection between agents and makes the system auditable.

```python
@dataclass
class AgentMessage:
    message_id: str           # UUID
    sender_agent: str         # "INTAKE" | "RESEARCH" | "EXECUTION" | "ESCALATION"
    recipient_agent: str      # Same enum
    task_type: str            # "route" | "research" | "execute" | "escalate"
    payload: dict             # Task-specific structured data
    context: dict             # Accumulated context from prior agents
    trace_id: str             # Links all messages in a task chain
    created_at: str           # ISO-8601
    ttl_seconds: int = 300    # Task expires if not completed
```

---

## 5. Core Task Flows

### 5.1 Flow A — Slack Request → Jira Ticket Creation

```
1. User: "@aibot create a ticket for the auth bug James mentioned"
2. INTAKE AGENT:
   - Extract intent: CREATE_TICKET
   - Extract entities: {type: "bug", subject: "auth", mentioned_by: "James"}
   - Pass to ORCHESTRATOR
3. ORCHESTRATOR:
   - Route to RESEARCH AGENT: "Find recent Slack messages from James about auth"
   - Receive context: {message_link, description, channel, timestamp}
   - Route to EXECUTION AGENT: "Create Jira ticket with this context"
4. EXECUTION AGENT:
   - POST /jira/issue with structured payload
   - Reply in Slack thread: "Ticket JRA-1234 created → [link]"
5. Log full trace to audit store
```

### 5.2 Flow B — Weekly Status Summary Generation

```
Schedule: Every Monday 08:00
1. ORCHESTRATOR triggers RESEARCH AGENT:
   - Query: Jira issues updated in last 7 days (by project/team)
   - Query: Notion pages modified in last 7 days
   - Query: Calendar events completed last week
2. RESEARCH AGENT returns structured data bundle
3. ORCHESTRATOR passes bundle to EXECUTION AGENT with template:
   - "Generate weekly status update in this format: {template}"
4. EXECUTION AGENT:
   - Posts summary to #weekly-status Slack channel
   - Creates/updates Notion status page
5. Flag for human review (ESCALATION AGENT sends DM to team lead)
```

### 5.3 Flow C — Ambiguous Request → Escalation

```
1. User: "@aibot sort out the thing with the vendor"
2. INTAKE AGENT: Confidence score < 0.60 on intent extraction
3. ORCHESTRATOR: Route to ESCALATION AGENT
4. ESCALATION AGENT:
   - Extract what IS known: {requester, channel, timestamp}
   - Draft clarification request
   - DM requester: "I wasn't sure how to handle this — can you clarify: [options]?"
5. Await response → re-enter intake flow
```

---

## 6. Tool Registry

Agents may only invoke tools present in the approved registry. Any tool call not in this registry is blocked and logged.

```yaml
# tool_registry.yaml
tools:
  jira_create_issue:
    description: "Create a new Jira issue"
    allowed_agents: [EXECUTION]
    rate_limit: 20/hour
    required_params: [project_key, summary, issue_type]

  jira_update_issue:
    description: "Update an existing Jira issue"
    allowed_agents: [EXECUTION]
    rate_limit: 30/hour
    required_params: [issue_key]

  jira_search:
    description: "JQL query against Jira"
    allowed_agents: [RESEARCH]
    rate_limit: 60/hour
    required_params: [jql_query]

  notion_create_page:
    description: "Create a new Notion page"
    allowed_agents: [EXECUTION]
    rate_limit: 10/hour
    required_params: [parent_id, title, content]

  notion_search:
    description: "Full-text search across Notion workspace"
    allowed_agents: [RESEARCH]
    rate_limit: 30/hour
    required_params: [query]

  slack_post_message:
    description: "Post a message to a Slack channel"
    allowed_agents: [EXECUTION, ESCALATION]
    rate_limit: 40/hour
    required_params: [channel_id, text]

  slack_send_dm:
    description: "Send a direct message to a user"
    allowed_agents: [ESCALATION]
    rate_limit: 10/hour
    required_params: [user_id, text]
```

---

## 7. Escalation Logic

### 7.1 Escalation Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| Low intent confidence | Score < 0.60 | Clarification DM to requester |
| Tool call failure | 2 consecutive failures | Notify task owner, pause |
| Missing required context | RESEARCH returns empty | Ask for clarification |
| Task TTL exceeded | Agent chain > 5min | Escalate to human with trace |
| Sensitive entity detected | PII, financial, legal keywords | Route to ESCALATION regardless |
| Scope creep | Task requires action outside tool registry | Decline + explain |

### 7.2 Escalation Package Format

When escalating to a human, the ESCALATION AGENT packages:

```json
{
  "trace_id": "trace_abc123",
  "original_request": "...",
  "what_was_understood": "...",
  "what_was_attempted": ["tool_1", "tool_2"],
  "why_escalating": "Low confidence on intent: 0.42",
  "suggested_actions": ["Option A", "Option B"],
  "context_bundle": {...},
  "requester": "user_xyz",
  "urgency": "LOW | MEDIUM | HIGH"
}
```

---

## 8. AutoGen v0.4 Implementation Notes

This system is built on **AutoGen v0.4** with a custom FastAPI orchestration layer.

### 8.1 Agent Initialization Pattern

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

model_client = OpenAIChatCompletionClient(model="qwen2.5:235b")  # via Ollama

intake_agent = AssistantAgent(
    name="IntakeAgent",
    model_client=model_client,
    system_message=INTAKE_SYSTEM_PROMPT,
    tools=[],  # INTAKE has no tools — read only
)

research_agent = AssistantAgent(
    name="ResearchAgent",
    model_client=model_client,
    system_message=RESEARCH_SYSTEM_PROMPT,
    tools=[jira_search, notion_search],
)

execution_agent = AssistantAgent(
    name="ExecutionAgent",
    model_client=model_client,
    system_message=EXECUTION_SYSTEM_PROMPT,
    tools=[jira_create_issue, jira_update_issue, notion_create_page, slack_post_message],
)
```

### 8.2 Orchestration via RoundRobinGroupChat

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination

termination = TextMentionTermination("TASK_COMPLETE") | TextMentionTermination("ESCALATE")

team = RoundRobinGroupChat(
    participants=[intake_agent, research_agent, execution_agent],
    termination_condition=termination,
    max_turns=10,
)
```

---

## 9. Implementation Plan

### Phase 1 — Skeleton (Week 1–2)
- [ ] Stand up FastAPI orchestration service
- [ ] Implement `AgentMessage` envelope and trace logging
- [ ] Build INTAKE and RESEARCH agents (no write access)
- [ ] Integration test against Jira sandbox + Notion sandbox

### Phase 2 — Execution (Week 3–4)
- [ ] Add EXECUTION agent with scoped tool registry
- [ ] Implement Flow A: Slack → Jira ticket creation
- [ ] Rate limiting + tool call logging
- [ ] Error handling + retry logic

### Phase 3 — Escalation & Status (Week 5–6)
- [ ] Build ESCALATION agent
- [ ] Implement Flow B: weekly status generation
- [ ] Implement Flow C: ambiguous request handling
- [ ] End-to-end latency profiling

### Phase 4 — Hardening (Week 7–8)
- [ ] Security review: inter-agent prompt injection test
- [ ] Load test: 100 concurrent task chains
- [ ] Human review of 500 resolved tasks (sampling)
- [ ] Adjust escalation thresholds based on data

---

## 10. Success Criteria — Launch Readiness

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Task completion rate | > 85% without escalation | Task resolution log |
| Escalation rate | < 15% | Same |
| End-to-end latency (P95) | < 45 seconds | Trace timestamps |
| Tool call accuracy | > 95% correct tool + params | Agent audit log |
| Zero unauthorized tool invocations | 100% | Registry enforcement test |
| Human satisfaction (sampled) | > 4.0/5.0 | Spot review survey |
