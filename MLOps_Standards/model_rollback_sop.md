# Model Rollback SOP — Zero-Downtime Procedure
**Version:** 1.0  
**Owner:** AI Platform / MLOps  
**Last Updated:** 2025-05  
**Applies To:** All LLM inference deployments (Ollama, vLLM, Azure OpenAI gateway)

---

## When to Execute This SOP

This procedure is triggered by **any** of the following conditions:

| Trigger | Source | Threshold |
|---------|--------|-----------|
| Hallucination rate spike | Eval monitoring | > 5% over 1-hour window |
| P95 latency regression | Prometheus | > 150% of 7-day baseline |
| Self-consistency drop | Eval harness | Score < 0.70 for 20+ consecutive calls |
| Critical safety failure | Human review | Any single confirmed unsafe output |
| Eval gate failure post-deploy | CI alert | Golden set score drops > 15% |
| Explicit on-call decision | PagerDuty | On-call engineer judgment |

**Do not wait for all metrics to confirm before initiating.** A single HIGH-severity trigger is sufficient to start this procedure.

---

## Roles & Responsibilities

| Role | Responsibility |
|------|----------------|
| **On-Call MLOps Engineer** | Owns execution of this SOP end-to-end |
| **Platform Lead** | Approval authority for non-emergency rollbacks |
| **AI Product Lead** | Notified at Step 1; confirms user impact |
| **Security Lead** | Notified if trigger is safety/compliance related |

---

## Pre-Rollback Checklist

Before executing rollback, confirm:

- [ ] Current model version is identified: `MODEL_ID_CURRENT`
- [ ] Rollback target version is identified: `MODEL_ID_ROLLBACK`
- [ ] Rollback version is available in container registry (not purged)
- [ ] Rollback version's last known eval scores are documented
- [ ] Incident channel opened in Slack: `#ai-incident-[date]`
- [ ] AI Product Lead notified via DM

---

## Rollback Procedure

### Step 1 — Assess & Declare (T+0)

```bash
# Check current deployment state
docker ps --filter "name=ai-inference"
# or: kubectl get deployments -n ai-platform

# Pull current model tag
docker inspect ai-inference-ollama | jq '.[0].Config.Env' | grep MODEL_NAME

# Check eval dashboard for confirmation of trigger
open https://grafana.internal/d/ai-eval-dashboard
```

Post to `#ai-incident-[date]`:
```
🔴 ROLLBACK INITIATED
Trigger: [describe trigger]
Current model: [MODEL_ID_CURRENT]
Target rollback: [MODEL_ID_ROLLBACK]
On-call: @[your-name]
ETA to completion: ~15 minutes
```

---

### Step 2 — Shift Traffic to Previous Version (T+2)

**Canary approach (preferred):** Shift load balancer weight before container swap.

```bash
# If using Nginx upstream weight:
# Edit /etc/nginx/conf.d/ai-upstream.conf
upstream ai_inference {
    server green:8080 weight=0;   # New (bad) version → 0%
    server blue:8080  weight=100; # Previous version → 100%
}

nginx -s reload
```

**Docker Compose rollback:**
```bash
# Set rollback model version
export MODEL_NAME=qwen2.5:7b-previous-tag
export IMAGE_TAG=ai-inference-ollama:v1.2.3  # Last known good

# Pull confirmed rollback image
docker pull $IMAGE_TAG

# Swap container (zero downtime via --no-deps)
docker compose -f docker-compose.inference.yml \
    up -d --no-deps --force-recreate ollama

# Verify container is healthy
docker ps --filter "name=ai-inference-ollama"
docker logs ai-inference-ollama --tail=50
```

**Kubernetes rollback:**
```bash
# Roll back to previous deployment revision
kubectl rollout undo deployment/ai-inference -n ai-platform

# Monitor rollout
kubectl rollout status deployment/ai-inference -n ai-platform --timeout=5m

# Verify pods
kubectl get pods -n ai-platform -l app=ai-inference
```

---

### Step 3 — Validate Rollback (T+8)

Run immediate smoke test against rollback version:

```bash
# Quick inference test
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "prompt": "What is 2 + 2? Answer in one word.",
    "stream": false
  }' | jq '.response'

# Run mini eval set (5 golden examples)
python evals/run_smoke_eval.py --n 5 --model $MODEL_NAME
```

Expected output: all 5 eval examples pass, no timeouts.

Check Prometheus panels:
- [ ] TTFT P95 within baseline range
- [ ] Hallucination rate metric dropping
- [ ] Error rate returning to normal

---

### Step 4 — Confirm & Communicate (T+12)

If validation passes:

```bash
# Tag the rollback as confirmed stable
docker tag $IMAGE_TAG ai-inference-ollama:stable-rollback
docker push ai-inference-ollama:stable-rollback
```

Post to `#ai-incident-[date]`:
```
✅ ROLLBACK COMPLETE
Rollback model: [MODEL_ID_ROLLBACK]
Validation: PASSED (smoke eval 5/5)
Traffic: 100% on rollback version
Metrics: Returning to baseline
Status: RESOLVED
Next: Post-mortem scheduled for [date]
```

Update `#ai-ops` channel with brief summary.

---

### Step 5 — Post-Mortem (Within 48 Hours)

Document the following in the incident Notion page:

1. **Timeline** — When was the bad version deployed? When was the issue detected? When was rollback complete?
2. **Root cause** — What caused the regression? (model weights, prompt change, config drift)
3. **Detection gap** — Why wasn't this caught in the eval gate?
4. **Impact** — How many users/requests were affected? Any user-facing incidents?
5. **Action items** — What eval tests need to be added to prevent recurrence?

---

## Rollback Decision Matrix

| Severity | Who Approves | Target Completion |
|----------|-------------|-------------------|
| Critical (safety/PII) | On-call only (no approval needed) | < 5 minutes |
| High (eval regression) | On-call + Platform Lead | < 15 minutes |
| Medium (latency spike) | On-call + Platform Lead | < 30 minutes |
| Low (minor quality drop) | Platform Lead review | Next business day |

---

## Version Registry — Known Good Versions

| Model | Version Tag | Eval Score | Deployed | Notes |
|-------|-------------|------------|----------|-------|
| qwen2.5:7b | v1.2.3 | 0.91 | 2025-04-15 | Current stable |
| qwen2.5:7b | v1.1.0 | 0.88 | 2025-03-10 | Fallback |
| gpt-4o | 2025-04-01 | 0.94 | 2025-04-01 | Azure gateway |

*Update this table after every production deployment.*

---

## Appendix: Rollback Failure Scenarios

| Scenario | Response |
|----------|----------|
| Rollback image not in registry | Redeploy from source — contact Platform Lead |
| Rollback version also has issues | Escalate to Platform Lead, disable AI features temporarily |
| Load balancer config locked | Manual DNS failover — contact DevOps on-call |
| Redis PII store corrupted | Flush + restart Redis, accept brief session loss |
