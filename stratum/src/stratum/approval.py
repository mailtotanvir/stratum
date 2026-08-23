"""The approval boundary.

NO APPROVAL = NO SIDE EFFECT. The executor is structurally unreachable
until a real human decision has been recorded for the pending plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .planning import Plan


ApprovalDecision = Literal["granted", "rejected"]


@dataclass(frozen=True)
class ApprovalRecord:
    decision: ApprovalDecision
    decider: str
    plan_id: str


class ApprovalPolicy(Protocol):
    """Decides what to do with a plan awaiting approval."""

    def decide(self, execution_id: str, plan: Plan) -> ApprovalRecord: ...


class InteractiveApprovalPolicy:
    """Prompts the operator on the console. This is the product default."""

    def __init__(self, input_fn=None, output_fn=print) -> None:
        self._input = input_fn or input
        self._print = output_fn

    def decide(self, execution_id: str, plan: Plan) -> ApprovalRecord:
        self._print("\nPLAN")
        for line in plan.summary_lines():
            self._print(line)
        self._print(f"\nRationale: {plan.rationale}")
        while True:
            answer = (
                self._input(f"\nApprove plan for {execution_id}? [y/N] ")
                .strip()
                .lower()
            )
            if answer in ("y", "yes"):
                return ApprovalRecord("granted", "cli-operator", plan.id)
            if answer in ("n", "no", ""):
                return ApprovalRecord("rejected", "cli-operator", plan.id)
            self._print("Please answer 'y' or 'n'.")


class PreDecidedApprovalPolicy:
    """Returns a fixed decision. For tests and scripted demos ONLY —
    never as the primary acceptance path (see tests/acceptance)."""

    def __init__(self, decision: ApprovalDecision, decider: str = "pre-decided") -> None:
        self._decision = decision
        self._decider = decider

    def decide(self, execution_id: str, plan: Plan) -> ApprovalRecord:
        return ApprovalRecord(self._decision, self._decider, plan.id)
