# Strategic AI Platform Transition
> **Orchestrating the migration from deterministic SaaS to probabilistic AI orchestration layers.**

**Author:** Thomas J. McCarthy IV — AI/ML Technical Program Manager | Georgia Tech OMSCS (ML)  
**Stack:** Python · FastAPI · AutoGen · Ollama · Cloudflare · Azure Bot · Make.com · n8n  
**Focus Areas:** Agentic Systems · MLOps · Enterprise AI Governance · Multi-Model Orchestration

---

## Purpose

This repository is a **Documentation-as-Code portfolio** — a living specification set that demonstrates how I bridge the gap between enterprise AI strategy and engineering execution. Each artifact here is written to the standard I'd hand to a senior SWE or ML engineer: enough context to understand *why*, enough spec to know *what*, and enough architecture detail to start building *today*.

The transition this portfolio documents is the shift most enterprises are undergoing right now:

```
Deterministic SaaS Tools
        ↓
LLM-Augmented Workflows
        ↓
Probabilistic AI Orchestration Layers
        ↓
Autonomous Multi-Agent Systems
```

This is not theoretical. Every framework, SOP, and architecture here is grounded in hands-on delivery.

---

## 🚀 Execution Milestones

### Milestone 1: Governance & Security
- **Status:** `[ ] In Progress`
- **Deliverable:** [RBAC & Audit Log Spec for LLM Ingestion](./PRDs/01_Security_and_RBAC_Framework.md)
- **Impact:** Establishes "Enterprise DNA" in non-deterministic environments — role-scoped prompts, PII redaction at ingestion, immutable audit trails for LLM interactions.
- **Audience:** Security architects, compliance leads, platform engineers.

### Milestone 2: MLOps Infrastructure
- **Status:** `[ ] Planned`
- **Deliverable:** [Containerized Inference Workflow](./MLOps_Standards/docker_base_configs/) + [Model Rollback SOP](./MLOps_Standards/model_rollback_sop.md)
- **Impact:** Scalable, repeatable deployment of high-parameter models. Zero-downtime rollback. Portable across Ollama, vLLM, and Bedrock targets.
- **Audience:** MLOps engineers, DevOps, infrastructure leads.

### Milestone 3: Probabilistic Evaluation
- **Status:** `[ ] Planned`
- **Deliverable:** [Hallucination & Latency Monitoring Framework](./PRDs/02_Probabilistic_Evaluation_Logic.md)
- **Impact:** Replaces static roadmaps with data-driven performance metrics. Defines the eval harness that makes LLM outputs auditable and comparable over time.
- **Audience:** ML engineers, QA leads, product managers.

### Milestone 4: Agentic Orchestration
- **Status:** `[ ] Planned`
- **Deliverable:** [Multi-Agent Task Loop PRD](./PRDs/03_Multi_Agent_Orchestration_PRD.md) + [Agent Communication Matrix](./Architecture/agent_communication_matrix.md)
- **Impact:** Transitions from operational coordination to intelligent orchestration. Agents route, delegate, and resolve tasks across Notion, Slack, and Jira with minimal human-in-the-loop.
- **Audience:** Platform architects, integration engineers, AI product leads.

---

## Repository Map

```
/enterprise-ai-platform-transition
│
├── /PRDs                              # Engineer-executable product specs
│   ├── 01_Security_and_RBAC_Framework.md
│   ├── 02_Probabilistic_Evaluation_Logic.md
│   └── 03_Multi_Agent_Orchestration_PRD.md
│
├── /Architecture                      # System design artifacts
│   ├── deployment_flow.mermaid        # CI/CD + inference deployment topology
│   └── agent_communication_matrix.md  # Agent routing, trust levels, tool access
│
├── /MLOps_Standards                   # Repeatable ops playbooks
│   ├── docker_base_configs/           # Base Dockerfiles per inference target
│   │   ├── Dockerfile.ollama
│   │   ├── Dockerfile.vllm
│   │   └── docker-compose.inference.yml
│   └── model_rollback_sop.md          # Zero-downtime rollback procedure
│
├── /Portfolio_Summaries               # Exec-facing artifacts
│   └── executive_one_pagers/
│       ├── AI_Governance_Brief.md
│       └── Agentic_Platform_ROI.md
│
└── README.md                          # This file
```

---

## Design Principles

| Principle | Application |
|-----------|-------------|
| **Payload over Polish** | Every doc is written so an engineer can act on it without a meeting |
| **Non-Determinism by Design** | Architectures account for probabilistic outputs at every layer |
| **Observable by Default** | No inference path without a trace, eval metric, or audit log |
| **Rollback is a Feature** | MLOps SOPs treat rollback as a first-class deployment event |
| **Agent Trust is Earned** | Multi-agent systems have explicit trust tiers, not implicit access |

---

## Tech Stack Reference

| Layer | Tools |
|-------|-------|
| Agent Runtime | AutoGen v0.4, custom FastAPI orchestrator |
| LLM Inference | Ollama (Qwen2.5-235B), Azure OpenAI, Anthropic API |
| Orchestration | Make.com, n8n, custom Python task loops |
| Deployment | Docker, Cloudflare Tunnel, Azure Bot Framework |
| Evaluation | Custom eval harness (latency, hallucination, task completion) |
| Monitoring | Structured logging → SQLite → dashboard layer |

---

*For questions on implementation, integration, or extending any spec in this repo — open an issue or reach out directly.*
