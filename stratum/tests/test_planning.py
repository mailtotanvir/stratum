import pytest

from stratum.errors import PlanValidationError
from stratum.planning import parse_plan

VALID = """
{
  "rationale": "change greeting",
  "steps": [
    {"description": "read hello.py", "action_type": "read_file", "path": "hello.py", "risk": "low", "requires_approval": false},
    {"description": "update greeting", "action_type": "write_file", "path": "hello.py", "content_summary": "Hello -> Hello Stratum"},
    {"description": "run tests", "action_type": "run_command", "command": "python -m pytest -q", "risk": "medium"}
  ]
}
"""


def test_parse_valid_plan():
    plan = parse_plan(VALID, task_id="t1", provider="scripted", model="m1")
    assert plan.rationale == "change greeting"
    assert [s.action_type for s in plan.steps] == [
        "read_file", "write_file", "run_command"]
    # Mutation steps are force-flagged for approval.
    assert plan.steps[0].requires_approval is False
    assert all(s.requires_approval for s in plan.steps[1:])
    assert plan.steps[0].index == 1 and plan.steps[2].index == 3


def test_parse_rejects_non_json():
    with pytest.raises(PlanValidationError, match="not valid JSON"):
        parse_plan("I will read the file first...", task_id="t")


def test_parse_rejects_unknown_action_type():
    bad = '{"rationale":"r","steps":[{"action_type":"deploy_to_prod"}]}'
    with pytest.raises(PlanValidationError, match="unknown action_type"):
        parse_plan(bad, task_id="t")


def test_parse_rejects_write_without_path():
    bad = '{"rationale":"r","steps":[{"description":"x","action_type":"write_file","content_summary":"c"}]}'
    with pytest.raises(PlanValidationError, match="write_file requires 'path'"):
        parse_plan(bad, task_id="t")


def test_parse_rejects_escaping_path():
    bad = (
        '{"rationale":"r","steps":[{"description":"x","action_type":"write_file",'
        '"path":"../outside.py","content_summary":"c"}]}'
    )
    with pytest.raises(PlanValidationError, match="inside the repo"):
        parse_plan(bad, task_id="t")


def test_parse_rejects_command_without_command():
    bad = '{"rationale":"r","steps":[{"description":"x","action_type":"run_command"}]}'
    with pytest.raises(PlanValidationError, match="run_command requires 'command'"):
        parse_plan(bad, task_id="t")


def test_parse_tolerates_fenced_json():
    fenced = "```json\n" + VALID + "\n```"
    plan = parse_plan(fenced, task_id="t")
    assert len(plan.steps) == 3


def test_parse_rejects_empty_steps():
    bad = '{"rationale":"r","steps":[]}'
    with pytest.raises(PlanValidationError, match="must contain steps"):
        parse_plan(bad, task_id="t")
