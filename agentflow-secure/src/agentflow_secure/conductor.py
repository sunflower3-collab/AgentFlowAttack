"""AgentFlow conductor: D = <P, S, E, M>, following Lande & Strashnoy (2025, pp. 7-12).

The conductor holds no domain logic: all logic lives in the swarm description (JSON).
"""
import json

from .journal import Journal


PHASE_TYPES = {"Sequential", "Parallel"}
AGENT_FIELDS = ("role", "logic")


class SwarmError(ValueError):
    """The swarm description is invalid; the run does not start."""


def parse(swarm):
    """P: swarm description -> internal form (agents, phases, data). Validates structure only, not content."""
    for key in ("name", "agents", "logic"):
        if key not in swarm:
            raise SwarmError(f"Swarm description has no '{key}' field")
    for aid, agent in swarm["agents"].items():
        for key in AGENT_FIELDS:
            if not isinstance(agent.get(key), str):
                raise SwarmError(f"Agent '{aid}': field '{key}' is missing or not a string")
    for i, phase in enumerate(swarm["logic"]):
        if phase.get("type") not in PHASE_TYPES:
            raise SwarmError(f"Phase {i}: unknown type '{phase.get('type')}'")
        for aid in phase.get("agents", []):
            if aid not in swarm["agents"]:
                raise SwarmError(f"Phase {i}: unknown agent '{aid}'")
    return swarm


def schedule(swarm):
    """S: the sequence of phases; each phase is a list of agents."""
    return [phase["agents"] for phase in swarm["logic"]]


def execute(agent, state, data, llm):
    """E(a, s, d) -> r. prompt_i = role + logic + state + input (Lande & Strashnoy, 2025, p. 9).

    Returns r and a record of the model call for the journal.
    """
    prompt = build_prompt(agent, state, data)
    try:
        response = llm.complete(prompt)
    except Exception as exc:  # any backend error becomes a result with status "error"
        error = f"{type(exc).__name__}: {exc}"
        return {"output": None, "status": "error", "error": error}, {"prompt": prompt, "error": error}
    call = {
        "prompt": prompt,
        "response": response.text,
        "model": response.model,
        "system_fingerprint": response.system_fingerprint,
        "finish_reason": response.finish_reason,
        "response_id": response.response_id,
        "usage": response.usage,
    }
    return {"output": response.text, "status": "success"}, call


def build_prompt(agent, state, data):
    """prompt_i = role + logic + state + input; state and input are rendered as readable text
    (as in Lande & Strashnoy, 2025, pp. 5-6), not as a dict repr()."""
    return f"{agent['role']}\n{agent['logic']}\nState:\n{render(state)}\nInput:\n{render(data)}"


def render(value, indent=0):
    """Deterministic readable rendering: "key: value" in the swarm description's key order.

    Strings are inserted verbatim (real line breaks, no escaping); other scalars and lists as JSON.
    """
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return f"{pad}(empty)"
        lines = []
        for key, item in value.items():
            if isinstance(item, dict) and item:
                lines.append(f"{pad}{key}:\n{render(item, indent + 1)}")
            else:
                lines.append(f"{pad}{key}: {render(item)}")
        return "\n".join(lines)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def update_state(state, result):
    """M: s(t+1) = M(s(t), r)."""
    new_state = dict(state)
    new_state["invocation_count"] = new_state.get("invocation_count", 0) + 1
    if result["status"] == "error":
        new_state["errors"] = new_state.get("errors", []) + [result["error"]]
    return new_state


def run_swarm(swarm, llm, journal_path):
    swarm = parse(swarm)
    journal = Journal(journal_path)
    try:
        journal.write("run_start", swarm=swarm["name"])
        states = {aid: dict(agent.get("state", {})) for aid, agent in swarm["agents"].items()}
        final = {}
        for phase in schedule(swarm):
            # The phase input is frozen before the phase starts: agents in one phase do not see each other's results.
            phase_input = {"data": swarm.get("data", {}), "results": {aid: r["result"]["output"] for aid, r in final.items()}}
            phase_results = {}
            for aid in phase:
                result, call = execute(swarm["agents"][aid], states[aid], phase_input, llm)
                journal.write("llm_call", agent_id=aid, **call)
                states[aid] = update_state(states[aid], result)
                phase_results[aid] = {"agent_id": aid, "result": result, "state": states[aid]}
            final.update(phase_results)
        errors = sum(r["result"]["status"] == "error" for r in final.values())
        status = "completed_with_errors" if errors else "completed"
        journal.write("run_end", status=status, errors=errors)
    finally:
        journal.close()
    return {"swarm": swarm["name"], "status": status, "errors": errors, "final_result": final, "journal": str(journal_path)}
