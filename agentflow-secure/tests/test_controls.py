"""Single-agent control: the same attack (same data) on one agent instead of the swarm."""
import copy
import json
from pathlib import Path

from agentflow_secure.conductor import run_swarm
from agentflow_secure.controls import single_agent_variant
from agentflow_secure.llm import StubLLM

ROOT = Path(__file__).parents[1]
SPEC = json.loads((ROOT / "configs" / "single_agent_control.json").read_text(encoding="utf-8"))["agent"]


def attack_swarm():
    swarm = json.loads((ROOT / "tests" / "data" / "lande2025b_complex_scenario.json").read_text(encoding="utf-8"))
    swarm["name"] = "A99_test"
    swarm["data"]["news_text"] = "The company announced record profits.\nInjected line."
    return swarm


def test_single_agent_control_runs_one_call_on_the_same_untrusted_data(tmp_path):
    swarm = attack_swarm()
    llm = StubLLM(reply="conclusion")
    result = run_swarm(single_agent_variant(swarm, SPEC), llm=llm, journal_path=tmp_path / "run.jsonl")

    assert len(llm.prompts) == 1
    assert llm.prompts[0].startswith("Report Generation\nAnalyze the trend of the time series")
    assert "news_text: The company announced record profits.\nInjected line." in llm.prompts[0]
    assert list(result["final_result"]) == ["agent_4"]
    assert result["swarm"] == "A99_test"


def test_single_agent_variant_does_not_modify_the_attack():
    swarm = attack_swarm()
    before = copy.deepcopy(swarm)
    single_agent_variant(swarm, SPEC)
    assert swarm == before
