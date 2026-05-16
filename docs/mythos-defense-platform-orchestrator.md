# Orchestrator Architecture Deep Dive

**Companion to the Mythos Defense Platform Blueprint**

---

## Why This Document Exists

The agents do the work. The sandbox contains them. The orchestrator is what makes the whole thing a system rather than a collection of scripts.

Everything that matters operationally happens at the orchestrator layer: agents are invoked with the right context, state is persisted across failures, budgets are enforced, human approval gates actually gate things, and every action is recorded in a way that can be audited months later. Get this layer wrong and the platform cannot be reasoned about, cannot be debugged, cannot be trusted.

This document specifies the orchestrator design in enough detail to implement it.

---

## Design Goals

The orchestrator must satisfy these properties:

**Durable.** Workflows survive process restarts, node failures, and deployment rollouts. A Red Team session that takes 30 minutes cannot be lost because a coordinator pod restarted at minute 20.

**Auditable.** Every decision, every agent invocation, every state transition, every tool call is recorded in an append-only log with cryptographic integrity. "What did the platform do for workflow X?" must be answerable with total precision.

**Resumable.** If a workflow fails halfway, it can be resumed from the last checkpoint, not restarted from scratch. This matters for cost (agent sessions are expensive) and for correctness (some operations are not idempotent).

**Observable.** Operators can see, in real time, every active workflow, every agent state, every budget consumption, and every alert. No black boxes.

**Safe by default.** Approval gates are real gates. Budgets are real limits. Scope enforcement is centralized. Individual agents cannot accidentally or deliberately bypass platform controls.

**Composable.** New agents and new workflow shapes can be added without rewriting the orchestrator. The agent roster will change; the orchestrator should not.

---

## Build vs. Buy

Three credible options:

### Option A: Temporal

**Fit:** Excellent. Temporal is a durable workflow engine designed for exactly this shape of problem: long-running, stateful orchestration of unreliable components.

**Pros:** Mature, battle-tested, SDKs in multiple languages, built-in retries and timers, strong observability story, open source with managed offering.

**Cons:** Learning curve. Workflow code must be deterministic, which takes discipline. Self-hosting is non-trivial at scale.

**Recommendation:** Strong default choice.

### Option B: LangGraph

**Fit:** Purpose-built for agent orchestration. Graph-based workflow definitions map naturally to the multi-agent pipeline.

**Pros:** First-class agent concepts. Integrates directly with LLM SDKs. Fast to prototype.

**Cons:** Newer, less battle-tested for high-stakes workloads. Durability story is weaker than Temporal. Operational maturity at scale is less proven.

**Recommendation:** Good for MVP and prototypes. Consider migration path to Temporal if scaling up.

### Option C: Build it yourself on Postgres + a queue

**Fit:** Possible, and some teams will prefer it.

**Pros:** No new dependency. Full control. Matches exact requirements.

**Cons:** You will rebuild Temporal poorly. Every non-trivial durability property must be engineered from scratch. Six months in, you will wish you had used Temporal.

**Recommendation:** Avoid unless you have a specific reason the above options don't fit.

The rest of this document assumes Temporal-style semantics — durable workflows, activities as the unit of side effect, signals for external input, timers, and retries. The concepts translate to LangGraph or a custom implementation if those are chosen.

---

## Core Abstractions

### Workflow

A workflow is a single security assessment from intake to completion. It has:

- A unique workflow ID
- A customer/tenant identifier
- A target (repository, codebase, brief)
- A configuration (which agents, which models, budget limits)
- A state (running, waiting, approved, rejected, completed, failed)
- A complete event history

Workflows are the unit of durability. They persist across restarts. They can be queried, paused, cancelled, and resumed.

### Activity

An activity is a single side effect — an agent invocation, a tool call, a sandbox provision, a database write. Activities are:

- Idempotent where possible (assigned a deterministic idempotency key)
- Retriable with configurable backoff
- Bounded in time (hard timeouts)
- Logged with inputs and outputs

The workflow code orchestrates activities. The workflow code itself does no I/O. All side effects go through activities.

### Signal

A signal is external input to a running workflow. Examples:

- Human approval of a proposed patch
- Cancellation request from a user
- Pause request from an operator
- Escalation response from a security engineer

Signals are how the outside world talks to a running workflow without breaking determinism.

### Timer

Timers are first-class. The orchestrator can sleep for arbitrary durations, wake up, and continue. This matters for approval gate timeouts, cost-budget windows, and polling patterns.

---

## Workflow Shapes

The platform runs several distinct workflow shapes. Each is defined separately.

### Shape 1: Full Site Assessment

```
receive_brief
  → architect_phase (Architect Agent)
  → human_approval_gate ("threat_model_signoff")
  → implementation_phase (Implementation Agent)
  → supply_chain_phase (Supply Chain Agent, parallel)
  → adversarial_loop (Red ↔ Blue until converged or budget exhausted)
  → deployment_phase (Deployment Agent)
  → human_approval_gate ("deployment_signoff")
  → final_report
```

### Shape 2: Existing Codebase Audit

```
receive_repo
  → reconnaissance_phase (structural analysis, tech stack detection)
  → threat_model_phase (Architect Agent adapted for existing code)
  → adversarial_loop
  → supply_chain_phase
  → findings_report
  → human_approval_gate ("disclosure_decision")
```

### Shape 3: Continuous Monitoring

```
on_repo_change
  → diff_analysis (determine scope of change)
  → incremental_threat_model_update
  → targeted_adversarial_loop (focused on changed files)
  → findings_delta_report
```

### Shape 4: Pre-Deployment Gate

```
receive_build_artifact
  → build_analysis
  → adversarial_loop (time-boxed)
  → gate_decision (pass/fail/escalate)
```

All shapes compose from the same set of activities. New shapes can be added without modifying the core.

---

## The Adversarial Loop as Orchestration Code

The adversarial loop described in the deep-dive document becomes concrete at this layer. In pseudocode:

```python
@workflow.defn
class AdversarialLoop:
    @workflow.run
    async def run(self, ctx: LoopContext) -> LoopResult:
        state = LoopState.from_context(ctx)
        clean_rounds = 0
        
        while not state.terminated():
            # RED phase — parallel by attack surface slice
            red_results = await asyncio.gather(*[
                workflow.execute_activity(
                    run_red_team_agent,
                    RedTeamInput(slice=s, context=state.context_for(s)),
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                for s in state.active_slices()
            ])
            
            # TRIAGE phase
            triaged = await workflow.execute_activity(
                triage_findings,
                TriageInput(findings=flatten(red_results), prior=state.all_findings),
                start_to_close_timeout=timedelta(minutes=5),
            )
            
            if not triaged.new_findings:
                clean_rounds += 1
                if clean_rounds >= state.required_clean_rounds:
                    return state.as_result(status="CONVERGED")
                continue
            
            clean_rounds = 0
            state.record_findings(triaged.new_findings)
            
            # BLUE phase — one finding at a time, priority order
            for finding in triaged.priority_order():
                if state.budget_exhausted():
                    return state.as_result(status="BUDGET_EXHAUSTED")
                
                patch = await workflow.execute_activity(
                    run_blue_team_agent,
                    BlueTeamInput(finding=finding, prior_attempts=state.attempts_for(finding)),
                    start_to_close_timeout=timedelta(minutes=20),
                )
                
                verified = await workflow.execute_activity(
                    verify_patch,
                    VerifyInput(patch=patch, poc=finding.poc),
                    start_to_close_timeout=timedelta(minutes=10),
                )
                
                if not verified.exploit_blocked:
                    state.record_patch_failure(finding, patch, verified.reason)
                    if state.patch_failures_for(finding) >= 3:
                        await workflow.execute_activity(
                            escalate_to_human,
                            EscalationInput(finding=finding, reason="unpatched_after_3_attempts"),
                        )
                    continue
                
                regression = await workflow.execute_activity(
                    run_regression_suite,
                    RegressionInput(patch=patch),
                    start_to_close_timeout=timedelta(minutes=15),
                )
                
                if regression.failed:
                    state.record_patch_failure(finding, patch, regression.reason)
                    continue
                
                state.record_fix(finding, patch)
            
            if state.iteration_count >= state.max_iterations:
                return state.as_result(status="ITERATION_CAP_HIT")
        
        return state.as_result(status=state.termination_reason)
```

Notes on this code:

- The workflow function contains no I/O. Every side effect is an activity.
- State is a deterministic data structure; `workflow.execute_activity` is the only source of non-determinism, and Temporal records its results in the event history.
- Retries are configured per activity, not globally.
- Timeouts are explicit everywhere. No activity can run forever.
- The loop has multiple termination conditions, all explicit.

---

## Agent Dispatch

Each agent invocation is an activity. Activities handle the messy details:

```python
@activity.defn
async def run_red_team_agent(input: RedTeamInput) -> RedTeamOutput:
    # 1. Provision sandbox
    sandbox = await sandbox_manager.provision(
        profile="red_team_max_isolation",
        code=input.code_snapshot,
        running_app=input.app_handle,
    )
    
    try:
        # 2. Build agent context with strict bounds
        context = AgentContext(
            system_prompt=load_prompt("red_team", slice=input.slice),
            user_prompt=format_assignment(input),
            tools=sandbox.permitted_tools(),
            budget=input.token_budget,
            timeout=input.wall_clock_budget,
        )
        
        # 3. Invoke the agent
        result = await anthropic_client.run_agent(
            model="claude-opus-4-7",
            context=context,
            tool_handlers=sandbox.tool_handlers(),
        )
        
        # 4. Extract findings through structured channel
        findings = sandbox.extract_artifacts(filter="finding_*")
        
        # 5. Validate each finding against schema
        validated = [f for f in findings if finding_schema.validate(f)]
        
        return RedTeamOutput(
            findings=validated,
            tokens_used=result.token_usage,
            wall_clock_seconds=result.elapsed,
            termination_reason=result.termination,
        )
    finally:
        # 6. Always destroy sandbox
        await sandbox_manager.destroy(sandbox)
```

This activity can be retried on transient failure (sandbox provisioning error, API timeout) without leaking sandboxes or double-charging budget. The `finally` ensures cleanup. The validation step rejects malformed findings before they reach the coordinator.

---

## Budget and Quota Enforcement

Budgets exist at multiple scopes. The orchestrator enforces all of them.

### Scope Hierarchy

```
Platform total (operator-set ceiling)
  └─ Tenant monthly (customer-set)
      └─ Workflow (workflow-configured)
          └─ Phase (e.g., adversarial loop)
              └─ Agent session (Red Team iteration)
                  └─ Tool call (API request)
```

Every level has:

- A hard limit (exceeded = termination)
- A soft warning threshold (exceeded = alert, no termination)
- A real-time accounting

### Enforcement Points

**Pre-flight check.** Before invoking an expensive activity, the workflow checks whether the activity can complete within remaining budget at every scope. If not, the activity is not invoked.

**In-flight monitoring.** Long-running activities (agent sessions) report progress. If the activity will exceed budget, the orchestrator signals it to wind down gracefully.

**Post-flight reconciliation.** After each activity, actual usage is deducted from all scopes. If reconciliation shows over-budget (due to reporting lag), subsequent activities may be denied.

### Cost Model

Every activity has an estimated cost function. For agent activities, this is a function of model, context size, and expected output. Estimates are conservative. Actual costs are tracked and compared to estimates; persistent over-runs drive estimate recalibration.

---

## Human Approval Gates

Approval gates are real gates. A workflow waiting on approval is genuinely paused — no agents running, no sandboxes consuming resources, no budget burning.

### Gate Lifecycle

```
workflow reaches gate
  → emit "approval_requested" event (includes full context for reviewer)
  → suspend workflow (Temporal-level suspension, not a polling loop)
  → reviewer sees request in dashboard / receives notification
  → reviewer submits signal (approve, reject, request_changes)
  → workflow resumes with the signal payload
```

### Gate Configurations

Different gates have different characteristics:

| Gate | Reviewer | Timeout | On timeout |
|------|----------|---------|------------|
| Threat model signoff | Customer | 7 days | Workflow cancelled |
| Deployment signoff | Customer | 3 days | Workflow cancelled |
| Disclosure decision | Customer | 14 days | Escalate to platform security |
| Escape suspicion | Platform security | 15 min | Kill sandbox, alert on-call |
| Policy override | Platform admin | 24 hr | Reject |

### Gate Bypass

Gates cannot be bypassed by agents. They can only be bypassed by explicit platform admin action, which is itself logged and requires dual-authorization (two admins must approve) for any gate marked as critical.

---

## Failure Handling

Failures are expected. The orchestrator handles them in structured ways.

### Failure Categories

**Transient.** API rate limit, sandbox provisioning glitch, network blip. Retry with exponential backoff.

**Persistent.** Repeated failures of the same activity. After configured retry limit, mark activity as failed and route to compensation logic.

**Contract violation.** Agent returned malformed output, sandbox crashed with corrupted state, tool call returned invalid response. No retry — this is a bug that needs investigation.

**Security.** Suspected sandbox escape, prompt injection, scope violation. Immediate termination, alert, quarantine.

**Budget.** Any budget exceeded. Graceful shutdown: finalize current activity, emit partial report, mark workflow as budget-terminated.

### Compensation

Some activities have side effects that require compensation on failure:

- Sandbox provisioned but workflow failed → destroy sandbox
- Credentials issued but session aborted → revoke credentials
- Partial findings committed but loop failed → mark findings as unverified
- External notification sent → send correction

Compensation logic is explicit in the workflow definition, not implicit. Every activity with external side effects declares its compensation activity.

### Dead-Letter Handling

Workflows that fail in non-recoverable ways land in a dead-letter queue. On-call engineers investigate. No auto-retry. The assumption is that non-recoverable failures indicate bugs, security issues, or operator errors — all of which need human attention.

---

## Event Sourcing and Audit

Every state change is an event. Events are the source of truth; current state is a projection.

### Event Schema

Every event has:

```
event_id: UUID
workflow_id: UUID
tenant_id: UUID
timestamp: ISO-8601 with monotonic sub-second precision
sequence: monotonically increasing within workflow
type: e.g., "agent_invoked", "finding_reported", "gate_requested"
actor: system component or user that caused the event
payload: type-specific structured data
prev_hash: hash of previous event in workflow
signature: HMAC or Ed25519 signature
```

The `prev_hash` and `signature` fields make the log tamper-evident. Any modification to historical events breaks the chain.

### Storage

Events go to an append-only store. Postgres with a logical-replication stream works well. For higher-scale deployments, use an event store purpose-built for this (EventStoreDB, Kafka with compaction, etc.).

Events are never deleted. Retention is handled by moving old events to cold storage (object storage with lifecycle policies), not by deletion.

### Queries

The event log supports several access patterns:

- Reconstruct state at any point in time for a workflow
- List all activity by a specific tenant in a time range
- Find all workflows that invoked a specific agent version
- Find all findings of a specific class
- Identify which prompts were used for which decisions

These queries are essential for debugging, compliance audits, and incident response.

### Retention and Compliance

Retention policy:

- Security-critical events (escape alerts, scope violations, approval decisions): 7 years
- Workflow events (agent invocations, findings, patches): 3 years
- Operational events (heartbeats, retries, timers): 90 days hot, 1 year cold

Compliance implications (SOC 2, PCI, customer data handling) depend on deployment. The event log makes these tractable; without it, they are nearly impossible.

---

## Multi-Tenancy

The orchestrator supports multiple tenants (customers) sharing the platform. Isolation must be real.

### Tenant Isolation Requirements

- No tenant can see another tenant's workflows, findings, or artifacts
- No tenant can consume another tenant's budget
- No tenant's agents run in sandboxes shared with another tenant's agents
- No tenant's credentials or secrets leak across tenant boundaries
- Tenant-scoped API keys that cannot access platform-wide resources

### Implementation

Row-level security at the database layer is the baseline. Every table that holds tenant data has `tenant_id` as a required column and RLS policies enforcing access. The orchestrator sets the tenant context at the start of every workflow and never drops out of it.

Network isolation at the sandbox layer enforces co-tenancy controls described in the sandboxing document.

Rate limiting, quota tracking, and billing attribution all happen per-tenant from the start. Adding multi-tenancy later is a significant rewrite; designing for it from day one is cheap.

---

## API Surface

External systems interact with the orchestrator through a narrow, well-defined API.

### Customer-Facing API

```
POST /v1/workflows                    # Create a new workflow
GET  /v1/workflows/{id}               # Get workflow state
GET  /v1/workflows/{id}/findings      # List findings
POST /v1/workflows/{id}/signals       # Send a signal (approve, cancel)
GET  /v1/workflows/{id}/events        # Stream or paginate event history
POST /v1/workflows/{id}/cancel        # Graceful cancellation
GET  /v1/workflows                    # List workflows (scoped to tenant)
```

### Operator-Facing API

```
GET  /admin/workflows                 # Cross-tenant workflow view
POST /admin/workflows/{id}/force      # Force-terminate (dual-auth required)
GET  /admin/budgets                   # Platform-level budget state
POST /admin/quarantine/{tenant}       # Quarantine a tenant (incident response)
GET  /admin/audit                     # Audit log query interface
```

### Webhook Surface

The platform emits webhooks for significant events:

- Workflow status transitions
- New findings of configured severity
- Approval requests
- Escape suspicions (customer-configured, default on for critical)
- Budget warnings and exhaustion

Webhooks are retried with exponential backoff and signed with per-tenant secrets.

---

## Observability

A few categories of observability, each with its own tooling:

### Metrics

- Workflow count by state, tenant, shape
- Activity latency distributions (p50, p95, p99) by activity type
- Agent token consumption by model, agent, tenant
- Sandbox provisioning time distribution
- Approval gate wait times
- Budget utilization by tenant

### Tracing

Every workflow generates a distributed trace spanning all activities. Individual agent sessions are sub-traces. Trace retention aligns with event retention: security-critical traces for years, operational traces for weeks.

### Logging

Structured logs at INFO for workflow lifecycle, WARN for degraded operation, ERROR for failures. Logs are not the source of truth — the event log is. Logs are for engineers debugging live.

### Dashboards

At minimum:

- Platform health overview (active workflows, error rates, budget burn)
- Tenant-specific dashboards (one per tenant, self-service)
- Security operations dashboard (escape alerts, policy violations, quarantines)
- Cost dashboard (per-tenant, per-workflow-shape breakdowns)

### Alerting

Alerts route to appropriate responders:

- Security alerts → on-call security engineer, paged immediately
- Workflow failures → engineering on-call, paged at threshold
- Budget warnings → account team, Slack notification
- Customer SLO misses → engineering on-call + account team

Every alert has an associated runbook. Alerts without runbooks are bugs in the observability stack.

---

## Deployment and Operations

### Deployment Model

The orchestrator runs as a stateless service (multiple replicas) backed by a stateful workflow engine (Temporal cluster or equivalent). Standard patterns apply: blue/green deploys, canary rollouts, automated rollback on error rate spikes.

Workflows in flight at deploy time must survive deploys. This is a property of the workflow engine, not the orchestrator code.

### Configuration Management

All configuration — agent versions, prompts, model selections, budget defaults, feature flags — is versioned and auditable. Prompts in particular should be treated like code: stored in version control, reviewed on change, deployed through the same pipeline as binaries.

### Prompt Versioning

Every agent invocation records the exact prompt version used. When prompts change, running workflows continue with the prompt version they started with (for reproducibility) while new workflows pick up the new version. A/B testing of prompts is a first-class feature, not a hack.

### Disaster Recovery

The orchestrator state is backed by the workflow engine's persistence plus the event log. Both have defined RPO and RTO:

- Event log: RPO 1 minute (via replication), RTO 15 minutes (restore from replica)
- Workflow engine: RPO 1 minute (via replication), RTO 30 minutes (standby cluster)

Agent sandboxes are ephemeral by design and not backed up. Lost in-flight sandboxes are an acceptable loss; the workflows resume with new sandboxes.

---

## What "Done" Looks Like

The orchestrator is sufficient when:

- Workflows survive coordinator restart, cluster failover, and deployment rollouts without data loss
- Every state change is captured in the event log, and state can be reconstructed from events alone
- Approval gates block progress without consuming resources
- Budget enforcement prevents runaway spending, tested with synthetic overruns
- Multi-tenant isolation has been independently reviewed and penetration tested
- Observability answers "what is happening right now" and "what happened yesterday at 3pm" with equal ease
- Runbooks exist for every alert type

Like the sandbox, this layer is never truly done. Workflow shapes will evolve, agents will change, and the orchestrator evolves with them.

---

## Relationship to Earlier Documents

This orchestrator sits between the pieces described in earlier documents:

- It invokes the agents described in the deep-dive document
- It provisions the sandboxes described in the sandboxing document
- It realizes the pipeline structure described in the blueprint

The three previous documents describe what. This one describes how it actually runs as a system — durably, safely, and observably.

---

*Document version 1.0 — companion to mythos-defense-platform-blueprint.md, mythos-defense-platform-deep-dive.md, and mythos-defense-platform-sandboxing.md*
