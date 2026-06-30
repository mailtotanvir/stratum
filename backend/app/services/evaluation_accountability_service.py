from datetime import UTC, datetime

from app.models.evaluation_accountability import (
    AccountabilityDecisionRecord,
    AccountabilityScorecard,
    EvaluationAccountabilityProjection,
    EvaluationRun,
    EvaluationRunCreate,
    EvaluationScenario,
    EvaluationScenarioCreate,
    RegressionFinding,
    RegressionSummary,
)
from app.models.runtime_event import EventType
from app.services.event_service import EventService, event_service


SCENARIO_REGISTERED = "evaluation_scenario_registered"
EVALUATION_RUN_RECORDED = "evaluation_run_recorded"
DECISION_ACCOUNTABILITY_RECORDED = "decision_accountability_recorded"


class EvaluationScenarioAlreadyExistsError(ValueError):
    pass


class EvaluationScenarioNotFoundError(LookupError):
    pass


class EvaluationRunNotFoundError(LookupError):
    pass


class EvaluationAccountabilityService:
    def __init__(self, events: EventService | None = None) -> None:
        self._events = events or event_service

    def register_scenario(self, request: EvaluationScenarioCreate) -> EvaluationScenario:
        scenarios = self.list_scenarios()
        scenario_id = request.scenario_id or f"scenario-{len(scenarios) + 1}"
        if any(s.scenario_id == scenario_id for s in scenarios):
            raise EvaluationScenarioAlreadyExistsError(
                f"Evaluation scenario already registered: {scenario_id}"
            )
        event = self._events.emit_event_sync(
            event_type=SCENARIO_REGISTERED,
            message="Evaluation scenario registered",
            metadata={**request.model_dump(exclude={"scenario_id"}), "scenario_id": scenario_id},
        )
        return _scenario_from_event(event.metadata, event.ts)

    def list_scenarios(self) -> list[EvaluationScenario]:
        return sorted(
            [_scenario_from_event(event.metadata, event.ts) for event in self._events.list_persisted_events(event_type=SCENARIO_REGISTERED)],
            key=lambda item: (item.created_at, item.scenario_id),
        )

    def get_scenario(self, scenario_id: str) -> EvaluationScenario:
        for scenario in self.list_scenarios():
            if scenario.scenario_id == scenario_id:
                return scenario
        raise EvaluationScenarioNotFoundError(scenario_id)

    def record_run(self, request: EvaluationRunCreate) -> EvaluationRun:
        scenario = self.get_scenario(request.scenario_id)
        run_id = request.run_id or f"evaluation-run-{len(self.list_runs()) + 1}"
        existing = {run.run_id for run in self.list_runs()}
        if run_id in existing:
            raise ValueError(f"Evaluation run already recorded: {run_id}")
        now = datetime.now(UTC)
        event = self._events.emit_event_sync(
            event_type=EVALUATION_RUN_RECORDED,
            message="Evaluation run recorded",
            metadata={
                **request.model_dump(exclude={"run_id"}),
                "run_id": run_id,
                "scenario_version": scenario.version,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        )
        return _run_from_event(event.metadata, event.ts)

    def list_runs(self) -> list[EvaluationRun]:
        return sorted(
            [_run_from_event(event.metadata, event.ts) for event in self._events.list_persisted_events(event_type=EVALUATION_RUN_RECORDED)],
            key=lambda item: (item.created_at, item.run_id),
        )

    def get_run(self, run_id: str) -> EvaluationRun:
        for run in self.list_runs():
            if run.run_id == run_id:
                return run
        raise EvaluationRunNotFoundError(run_id)

    def record_decision(self, decision_id: str, target_type: str, target_id: str, decision_summary: str, runtime_event_id: int | None = None) -> AccountabilityDecisionRecord:
        event = self._events.emit_event_sync(
            event_type=DECISION_ACCOUNTABILITY_RECORDED,
            message="Decision accountability recorded",
            metadata={
                "decision_id": decision_id,
                "target_type": target_type,
                "target_id": target_id,
                "decision_summary": decision_summary,
                "runtime_event_id": runtime_event_id,
            },
        )
        return _decision_from_event(event.metadata, event.ts)

    def list_decisions(self) -> list[AccountabilityDecisionRecord]:
        return sorted(
            [_decision_from_event(event.metadata, event.ts) for event in self._events.list_persisted_events(event_type=DECISION_ACCOUNTABILITY_RECORDED)],
            key=lambda item: (item.created_at, item.decision_id),
        )

    def build_projection(self) -> EvaluationAccountabilityProjection:
        scenarios = self.list_scenarios()
        runs = self.list_runs()
        decisions = self.list_decisions()
        scorecards = self._scorecards(runs)
        regressions = self._regressions(runs)
        return EvaluationAccountabilityProjection(
            metadata={
                "projection_type": "evaluation_accountability",
                "builder_name": "EvaluationAccountabilityService",
                "reconstruction": {
                    "projection_type": "evaluation_accountability",
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            scenarios=scenarios,
            runs=runs,
            scorecards=scorecards,
            regressions=regressions,
            decisions=decisions,
            generated_at=datetime.now(UTC),
        )

    def _scorecards(self, runs: list[EvaluationRun]) -> list[AccountabilityScorecard]:
        buckets: dict[tuple[str, str], list[EvaluationRun]] = {}
        for run in runs:
            buckets.setdefault((run.target_type, run.target_id), []).append(run)
        output = []
        for (target_type, target_id), items in sorted(buckets.items()):
            pass_count = sum(1 for item in items if item.outcome == "pass")
            fail_count = sum(1 for item in items if item.outcome == "fail")
            inconclusive_count = sum(1 for item in items if item.outcome == "inconclusive")
            scores = [item.score for item in items if item.score is not None]
            latest = max(items, key=lambda item: (item.created_at, item.run_id))
            output.append(
                AccountabilityScorecard(
                    target_type=target_type,
                    target_id=target_id,
                    evaluation_count=len(items),
                    pass_count=pass_count,
                    fail_count=fail_count,
                    inconclusive_count=inconclusive_count,
                    average_score=(sum(scores) / len(scores)) if scores else None,
                    latest_run_id=latest.run_id,
                    latest_outcome=latest.outcome,
                    latest_evaluated_at=latest.created_at,
                )
            )
        return output

    def _regressions(self, runs: list[EvaluationRun]) -> RegressionSummary:
        findings: list[RegressionFinding] = []
        grouped: dict[tuple[str, str], list[EvaluationRun]] = {}
        for run in runs:
            grouped.setdefault((run.target_type, run.target_id), []).append(run)
        repeated: dict[str, int] = {}
        for (target_type, target_id), items in sorted(grouped.items()):
            ordered = sorted(items, key=lambda item: (item.created_at, item.run_id))
            for baseline, comparison in zip(ordered, ordered[1:]):
                if baseline.score is not None and comparison.score is not None:
                    delta = comparison.score - baseline.score
                    status = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
                else:
                    delta = None
                    status = "inconclusive"
                signature = f"{target_type}:{target_id}:{comparison.outcome}"
                repeated[signature] = repeated.get(signature, 0) + (1 if comparison.outcome == "fail" else 0)
                findings.append(
                    RegressionFinding(
                        target_type=target_type,
                        target_id=target_id,
                        baseline_run_id=baseline.run_id,
                        comparison_run_id=comparison.run_id,
                        baseline_score=baseline.score,
                        comparison_score=comparison.score,
                        score_delta=delta,
                        status=status,
                        signature=signature,
                    )
                )
        indicators = []
        if any(item.status == "regressed" for item in findings):
            indicators.append("regression_detected")
        if any(item.status == "unchanged" for item in findings):
            indicators.append("flat_quality_surface")
        return RegressionSummary(
            total_targets=len(grouped),
            comparison_count=len(findings),
            regressed_count=sum(1 for item in findings if item.status == "regressed"),
            improved_count=sum(1 for item in findings if item.status == "improved"),
            unchanged_count=sum(1 for item in findings if item.status == "unchanged"),
            repeated_failure_signatures=[
                {"signature": signature, "count": count}
                for signature, count in sorted(repeated.items())
                if count > 0
            ],
            quality_drift_indicators=indicators,
            findings=findings,
            generated_at=datetime.now(UTC),
        )


def _scenario_from_event(metadata: dict, created_at: str) -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=str(metadata["scenario_id"]),
        title=str(metadata["title"]),
        purpose=str(metadata["purpose"]),
        input_fixture=str(metadata["input_fixture"]),
        expected_behavior=str(metadata["expected_behavior"]),
        rubric=str(metadata["rubric"]),
        target_type=metadata["target_type"],
        version=int(metadata["version"]),
        tags=list(metadata.get("tags", [])),
        risk_level=metadata["risk_level"],
        created_at=datetime.fromisoformat(created_at),
    )


def _run_from_event(metadata: dict, created_at: str) -> EvaluationRun:
    return EvaluationRun(
        run_id=str(metadata["run_id"]),
        scenario_id=str(metadata["scenario_id"]),
        target_type=metadata["target_type"],
        target_id=str(metadata["target_id"]),
        target_runtime_event_id=metadata.get("target_runtime_event_id"),
        evaluator=str(metadata["evaluator"]),
        evaluator_type=str(metadata["evaluator_type"]),
        outcome=metadata["outcome"],
        score=metadata.get("score"),
        evidence=list(metadata.get("evidence", [])),
        metadata=dict(metadata.get("metadata", {})),
        created_at=datetime.fromisoformat(created_at),
        updated_at=datetime.fromisoformat(metadata.get("updated_at", created_at)),
        scenario_version=int(metadata["scenario_version"]),
    )


def _decision_from_event(metadata: dict, created_at: str) -> AccountabilityDecisionRecord:
    return AccountabilityDecisionRecord(
        decision_id=str(metadata["decision_id"]),
        target_type=metadata["target_type"],
        target_id=str(metadata["target_id"]),
        decision_summary=str(metadata["decision_summary"]),
        runtime_event_id=metadata.get("runtime_event_id"),
        created_at=datetime.fromisoformat(created_at),
    )


evaluation_accountability_service = EvaluationAccountabilityService()
