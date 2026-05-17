"""V0 orchestrator — simple loop, not durable."""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from rich.console import Console

from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget
from mythos_defense.agents.architect import ArchitectAgent
from mythos_defense.agents.blue_team import BlueTeamAgent
from mythos_defense.agents.supply_chain import SupplyChainAgent
from mythos_defense.agents.deployment import DeploymentAgent
from mythos_defense.orchestrator.budget import Budget
from mythos_defense.orchestrator.verify import (
    apply_patch, verify_finding,
)
from mythos_defense.schemas.findings import Finding

console = Console()


@dataclass
class WorkflowConfig:
    workflow_id: str
    workspace: Path
    brief: str
    output_dir: Path
    budget: Budget = field(default_factory=Budget)


@dataclass
class WorkflowResult:
    workflow_id: str
    status: str  # CONVERGED|BUDGET_EXHAUSTED|ITERATION_CAP|ERROR
    threat_model: dict | None
    findings_history: list[list[Finding]]
    patches_applied: list[dict]
    unresolved_findings: list[Finding]
    supply_chain: dict | None
    deployment: dict | None
    duration_seconds: float


class Orchestrator:
    def __init__(self, red_team_adapter: RedTeamAdapter):
        self.red_team = red_team_adapter
        self.architect = ArchitectAgent()
        self.blue_team = BlueTeamAgent()
        self.supply_chain = SupplyChainAgent()
        self.deployment = DeploymentAgent()

    def run(self, cfg: WorkflowConfig) -> WorkflowResult:
        start = time.time()
        cfg.budget.started_at = start
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        console.print("[bold cyan]> Architect: producing threat model[/]")
        arch_result = self.architect.run(cfg.brief)
        cfg.budget.spend_tokens(arch_result.tokens_in + arch_result.tokens_out)
        threat_model = arch_result.structured
        (cfg.output_dir / "threat_model.json").write_text(
            json.dumps(threat_model, indent=2)
        )

        findings_history: list[list[Finding]] = []
        patches_applied: list[dict] = []
        excluded: list[str] = []
        clean_rounds = 0
        last_findings: list[Finding] = []

        for iteration in range(cfg.budget.max_iterations):
            cfg.budget.iterations = iteration + 1
            ok, reason = cfg.budget.can_continue()
            if not ok:
                console.print(f"[yellow]Budget halt: {reason}[/]")
                break

            console.print(f"[bold cyan]> Iteration {iteration}: Red Team adapter ({self.red_team.name})[/]")

            target = AdapterTarget(
                workspace=cfg.workspace,
                iteration=iteration,
                workflow_id=cfg.workflow_id,
                excluded_findings=excluded,
            )
            try:
                finding_set = self.red_team.run(target)
            except Exception as e:
                console.print(f"[red]Red Team adapter failed: {e}[/]")
                break

            new_findings = finding_set.findings
            findings_history.append(new_findings)

            if not new_findings:
                clean_rounds += 1
                console.print(f"[green]Clean round {clean_rounds}[/]")
                if clean_rounds >= 2:
                    return self._finalize(cfg, "CONVERGED", threat_model, findings_history,
                                          patches_applied, [], start)
                continue

            clean_rounds = 0
            console.print(f"[yellow]Found {len(new_findings)} findings[/]")
            last_findings = new_findings

            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
            for finding in sorted(new_findings, key=lambda f: severity_order.get(f.severity.value, 99)):
                if not cfg.budget.can_attempt_patch(finding.finding_id):
                    console.print(f"[red]Skip {finding.finding_id}: max attempts reached[/]")
                    continue

                console.print(f"[bold cyan]> Blue Team: {finding.finding_id} ({finding.severity})[/]")
                cfg.budget.record_attempt(finding.finding_id)

                try:
                    blue_result = self.blue_team.run(finding, cfg.workspace)
                except Exception as e:
                    console.print(f"[red]Blue Team failed for {finding.finding_id}: {e}[/]")
                    continue

                cfg.budget.spend_tokens(blue_result.tokens_in + blue_result.tokens_out)
                patch = blue_result.structured

                if patch.get("requires_escalation"):
                    console.print(f"[magenta]Escalation: {patch.get('escalation_reason')}[/]")
                    continue

                ok = apply_patch(cfg.workspace, patch.get("files_changed", []))
                if not ok:
                    console.print(f"[red]Patch did not apply for {finding.finding_id}[/]")
                    continue

                verify_result = verify_finding(finding, cfg.workspace)

                patch_record = {
                    "finding_id": finding.finding_id,
                    "patch": patch,
                    "verify": {
                        "exploit_blocked": verify_result.exploit_blocked,
                        "details": verify_result.details,
                    },
                }
                patches_applied.append(patch_record)

                if verify_result.exploit_blocked:
                    excluded.append(finding.finding_id)
                    console.print(f"[green]PASS {finding.finding_id} verified blocked[/]")
                else:
                    console.print(f"[red]FAIL {finding.finding_id} not blocked: {verify_result.details[:200]}[/]")

        console.print("[bold cyan]> Supply Chain Agent[/]")
        try:
            sc_result = self.supply_chain.run(cfg.workspace)
            cfg.budget.spend_tokens(sc_result.tokens_in + sc_result.tokens_out)
            supply_chain = sc_result.structured
        except Exception as e:
            console.print(f"[red]Supply chain failed: {e}[/]")
            supply_chain = {"error": str(e)}

        console.print("[bold cyan]> Deployment Agent[/]")
        try:
            dep_result = self.deployment.run(cfg.brief, threat_model)
            cfg.budget.spend_tokens(dep_result.tokens_in + dep_result.tokens_out)
            deployment = dep_result.structured
        except Exception as e:
            console.print(f"[red]Deployment failed: {e}[/]")
            deployment = {"error": str(e)}

        unresolved = [f for f in last_findings if f.finding_id not in excluded]
        status = "CONVERGED" if not unresolved else "ITERATION_CAP"

        return self._finalize(
            cfg, status, threat_model, findings_history, patches_applied,
            unresolved, start, supply_chain=supply_chain, deployment=deployment,
        )

    def _finalize(
        self, cfg, status, threat_model, findings_history, patches_applied,
        unresolved, start, supply_chain=None, deployment=None,
    ) -> WorkflowResult:
        result = WorkflowResult(
            workflow_id=cfg.workflow_id,
            status=status,
            threat_model=threat_model,
            findings_history=findings_history,
            patches_applied=patches_applied,
            unresolved_findings=unresolved,
            supply_chain=supply_chain,
            deployment=deployment,
            duration_seconds=time.time() - start,
        )

        report = {
            "workflow_id": result.workflow_id,
            "status": result.status,
            "duration_seconds": result.duration_seconds,
            "threat_model": result.threat_model,
            "iterations": [
                [f.model_dump(mode="json") for f in iteration]
                for iteration in result.findings_history
            ],
            "patches": result.patches_applied,
            "unresolved": [f.model_dump(mode="json") for f in result.unresolved_findings],
            "supply_chain": result.supply_chain,
            "deployment": result.deployment,
        }
        (cfg.output_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
        return result
