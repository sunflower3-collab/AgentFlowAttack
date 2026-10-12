"""Control configurations for the demonstration."""
import copy


def single_agent_variant(swarm, agent):
    """Single-agent control: the same attack name and data, but one agent instead of the swarm.

    The trusted agent description comes from configs/single_agent_control.json; the untrusted data is unchanged.
    """
    return {
        "name": swarm["name"],
        "agents": {agent["id"]: copy.deepcopy(agent)},
        "logic": [{"type": "Sequential", "agents": [agent["id"]]}],
        "data": copy.deepcopy(swarm.get("data", {})),
    }
