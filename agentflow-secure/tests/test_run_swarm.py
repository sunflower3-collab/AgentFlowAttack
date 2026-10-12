import copy
import json
from pathlib import Path

import pytest

from agentflow_secure.conductor import SwarmError, run_swarm
from agentflow_secure.llm import LLMResponse, StubLLM

DATA = Path(__file__).parent / "data"


def load_lande_example():
    return json.loads((DATA / "lande2025b_complex_scenario.json").read_text(encoding="utf-8"))


def test_lande_example_produces_result_from_paper(tmp_path):
    # Expected result from Lande & Strashnoy (2025), pp. 15-16 (without the timestamp field).
    result = run_swarm(load_lande_example(), llm=StubLLM(reply="executed"), journal_path=tmp_path / "run.jsonl")

    assert result["swarm"] == "complex_scenario"
    expected_agent = lambda aid: {
        "agent_id": aid,
        "result": {"output": "executed", "status": "success"},
        "state": {"invocation_count": 1},
    }
    assert result["final_result"] == {aid: expected_agent(aid) for aid in ["agent_1", "agent_2", "agent_3", "agent_4"]}


class RecordingLLM(StubLLM):
    """Replies with the role name, so it is visible whose result went where."""

    def complete(self, prompt):
        self.prompts.append(prompt)
        role = prompt.splitlines()[0]
        return LLMResponse(text=f"out:{role}")


def prompt_of(llm, role):
    return next(p for p in llm.prompts if p.startswith(role))


def test_results_flow_to_later_phases_but_not_within_parallel_phase(tmp_path):
    llm = RecordingLLM()
    run_swarm(load_lande_example(), llm=llm, journal_path=tmp_path / "run.jsonl")

    report = prompt_of(llm, "Report Generation")
    for upstream in ["Data Preparation", "Time Series Analysis", "Text Analysis"]:
        assert f"out:{upstream}" in report
    # agents in one parallel phase do not see each other's results (Lande & Strashnoy, 2025, pp. 11, 14)
    assert "out:Time Series Analysis" not in prompt_of(llm, "Text Analysis")
    assert "out:Data Preparation" in prompt_of(llm, "Text Analysis")



def broken(mutate):
    swarm = copy.deepcopy(load_lande_example())
    mutate(swarm)
    return swarm


@pytest.mark.parametrize(
    "swarm",
    [
        broken(lambda s: s["logic"].append({"type": "Sequential", "agents": ["agent_9"]})),
        broken(lambda s: s["logic"].append({"type": "Loop", "agents": ["agent_1"]})),
        broken(lambda s: s["agents"]["agent_2"].pop("logic")),
        broken(lambda s: s.pop("logic")),
    ],
    ids=["unknown-agent", "unknown-phase-type", "agent-without-logic", "no-logic"],
)
def test_invalid_swarm_is_rejected_before_any_llm_call(swarm, tmp_path):
    llm = StubLLM()
    with pytest.raises(SwarmError):
        run_swarm(swarm, llm=llm, journal_path=tmp_path / "run.jsonl")
    assert llm.prompts == []


class FailingLLM(StubLLM):
    """Fails on the given role, replies 'executed' to the rest."""

    def __init__(self, fail_role):
        super().__init__()
        self.fail_role = fail_role

    def complete(self, prompt):
        self.prompts.append(prompt)
        if prompt.startswith(self.fail_role):
            raise TimeoutError("LLM timeout")
        return LLMResponse(text="executed")


def test_llm_failure_is_recorded_as_error_result_and_run_continues(tmp_path):
    # Error result format and recording the error in state follow Lande & Strashnoy (2025).
    result = run_swarm(load_lande_example(), llm=FailingLLM("Text Analysis"), journal_path=tmp_path / "run.jsonl")

    failed = result["final_result"]["agent_3"]
    assert failed["result"] == {"output": None, "status": "error", "error": "TimeoutError: LLM timeout"}
    assert failed["state"]["errors"] == ["TimeoutError: LLM timeout"]
    assert result["final_result"]["agent_4"]["result"]["status"] == "success"


def read_journal(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class UsageStubLLM(StubLLM):
    def complete(self, prompt):
        self.prompts.append(prompt)
        return LLMResponse(text="executed", usage={"prompt_tokens": 12, "completion_tokens": 3}, model="test-model")


def test_journal_records_each_model_request_response_and_tokens(tmp_path):
    journal = tmp_path / "run.jsonl"
    result = run_swarm(load_lande_example(), llm=UsageStubLLM(), journal_path=journal)

    records = read_journal(journal)
    assert [r["event"] for r in records] == ["run_start", "llm_call", "llm_call", "llm_call", "llm_call", "run_end"]
    calls = [r for r in records if r["event"] == "llm_call"]
    assert [c["agent_id"] for c in calls] == ["agent_1", "agent_2", "agent_3", "agent_4"]
    first = calls[0]
    assert first["prompt"].startswith("Data Preparation\nClean the data and convert it into a structured format.")
    assert first["response"] == "executed"
    assert first["model"] == "test-model"
    assert first["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}
    assert result["journal"] == str(journal)


def test_run_with_failed_agents_is_reported_as_failed_not_completed(tmp_path):
    journal = tmp_path / "run.jsonl"
    result = run_swarm(load_lande_example(), llm=FailingLLM("Text Analysis"), journal_path=journal)

    assert result["status"] == "completed_with_errors"
    assert result["errors"] == 1
    run_end = read_journal(journal)[-1]
    assert (run_end["status"], run_end["errors"]) == ("completed_with_errors", 1)


def test_clean_run_is_reported_as_completed(tmp_path):
    result = run_swarm(load_lande_example(), llm=StubLLM(), journal_path=tmp_path / "run.jsonl")
    assert (result["status"], result["errors"]) == ("completed", 0)


def test_input_data_is_given_to_the_model_as_readable_text(tmp_path):
    # Input data is rendered as readable text (as in Lande & Strashnoy, 2025, pp. 5-6), not a dict repr().
    swarm = copy.deepcopy(load_lande_example())
    swarm["data"]["news_text"] = "The company announced record profits.\nSecond line of the article."
    llm = RecordingLLM()
    run_swarm(swarm, llm=llm, journal_path=tmp_path / "run.jsonl")

    prompt = prompt_of(llm, "Text Analysis")
    assert "news_text: The company announced record profits.\nSecond line of the article." in prompt
    assert "time_series: [100, 105, 110, 115, 120]" in prompt
    assert "\\n" not in prompt and "{'" not in prompt  # no escaped newlines and no dict repr()
    report = prompt_of(llm, "Report Generation")
    assert "agent_3: out:Text Analysis" in report


def test_exact_prompts_for_lande_example_are_pinned(tmp_path):
    # Pins the full prompt_i format (labelled sections, as in AgentFlowLaw).
    llm = StubLLM(reply="executed")
    run_swarm(load_lande_example(), llm=llm, journal_path=tmp_path / "run.jsonl")

    data_block = (
        "Input:\n"
        "data:\n"
        "  time_series: [100, 105, 110, 115, 120]\n"
        "  news_text: The company announced record profits.\n"
    )
    assert llm.prompts[0] == (
        "Data Preparation\n"
        "Clean the data and convert it into a structured format.\n"
        "State:\n(empty)\n" + data_block + "results: (empty)"
    )
    assert llm.prompts[3] == (
        "Report Generation\n"
        "Combine all results into a final conclusion.\n"
        "State:\n(empty)\n" + data_block +
        "results:\n  agent_1: executed\n  agent_2: executed\n  agent_3: executed"
    )
