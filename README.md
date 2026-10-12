# AgentFlowAttack

A prompt-injection demonstration against a reproduction of the base conductor of the no-code AgentFlow framework.

> **New here?** Start with the step-by-step **[guided walkthrough](GUIDE.md)** — it explains, in plain words, what was done, why it was done that way, and what you get at each step.

<p align="center">
  <img src="prompt-anatomy.svg" alt="Anatomy of one agent's prompt: the trusted role and logic sit in the same prompt as the untrusted news_text, which carries a hidden instruction; the model follows it and prints the marker." width="840">
</p>

## What this is

This repository is an academic demonstration of how prompt injection affects an agent swarm built on the base model of the AgentFlow framework. The testbed is a small, self-written Python conductor that reproduces how AgentFlow executes a swarm, as described in the papers by Lande and Strashnoy. All attacks run only on an isolated testbed with a synthetic scenario. The repository contains the testbed code, the attack set, one example transcript per attack, a results summary, and the commands to re-check everything. The full story is in the [guided walkthrough](GUIDE.md).

## Key result

Nine injection templates (A01-A09) were placed into the swarm's only untrusted field (a news text) and run 5 times in two modes: the full four-agent swarm, and a single agent given the same text.

| Metric | Swarm | Single agent |
|---|---|---|
| Attack success by marker (9 templates × 5 repeats) | 45/45 | 45/45 |
| Same, excluding the adaptive attack A09 | 40/40 | 40/40 |
| False positives on the negative control A00 | 0/5 | 0/5 |

Success means the swarm's final conclusion contains a marker string that can only appear if the model executed the instruction hidden in the data — so it measures **output integrity** (the model followed a foreign instruction), not a harmful action, since the testbed has no tools. The numbers were independently re-scored from the run journals with a full match. The machine-readable results are in [`results/2026-10-11-C0-series/summary.json`](results/2026-10-11-C0-series/summary.json); a worked example is in [`examples/`](examples/) and the full explanation in the [guided walkthrough](GUIDE.md).

What this result does **not** show:
- **Not propagation between agents.** The final agent reads the news text directly, so a hit does not prove the injection travelled from agent to agent.
- **Not a flaw in AgentFlow in general.** This is one base scenario and one model. The susceptibility is a property of a single LLM call that mixes trusted instructions and untrusted data in one prompt; the swarm adds neither protection nor extra vulnerability.
- The five repeats are **not independent samples**, so the numbers show the stability of the effect, not an overall success frequency. The temperature was fixed at 0, and the detector catches only injections aimed at a string in the output.

## What AgentFlow is

AgentFlow is a no-code framework by D. Lande and L. Strashnoy in which agent logic is defined by prompts and executed by a universal conductor that is the same across all scenarios. This repository reproduces the base conductor defined in the second paper below (*Orchestration…*): D = ⟨P, S, E, M⟩, where each agent is a single LLM call and the base framework has no tool-calling. The third paper's code / small-model execution is deliberately not implemented.
- [SSRN 10.2139/ssrn.5285664](https://doi.org/10.2139/ssrn.5285664) — No-Code Agent Framework Based on Logical Primitives
- [SSRN 10.2139/ssrn.5381820](https://doi.org/10.2139/ssrn.5381820) — Orchestration of No-Code Agents in the AgentFlow Framework
- [SSRN 10.2139/ssrn.5522698](https://doi.org/10.2139/ssrn.5522698) — Extension of the Universal Conductor for Heterogeneous Execution Environments
- [github.com/DmytroLande/AgentFlowLaw](https://github.com/DmytroLande/AgentFlowLaw) — the AgentFlowLaw repository

This is an independent research demonstration and is not an official part of AgentFlow.

## Reproduce

Step-by-step instructions, with what you get at each step, are in the guided walkthrough: **[Do it yourself](GUIDE.md#9-do-it-yourself)**. In short, from a git clone (Windows PowerShell, Python 3.14):

```powershell
cd agentflow-secure
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```

The tests (`37 passed`) run offline, with no key and no cost. Then read the transcripts in [`examples/`](examples/), or run the attacks live with your own OpenAI key (see the guide).

## Repository layout

```
GUIDE.md            step-by-step guided walkthrough (start here)
prompt-anatomy.svg  the diagram above: one agent's prompt, trusted instructions vs untrusted data
agentflow-secure/   testbed code: conductor, detector, scoring, tests, configs
attacks/            attack set A00–A09 and manifest.json describing the attacks, detector, and criteria
examples/           one representative transcript per attack: the untrusted input and every agent's output
results/            the run summary (summary.json) and a README of the series
```

A full, annotated file list is in the [guided walkthrough](GUIDE.md#10-what-is-in-this-repository).

## License

MIT (see the [LICENSE](LICENSE) file).

## How to cite

sunflower3-collab. AgentFlowAttack: a prompt-injection demonstration against a reproduction of the AgentFlow conductor [online]. GitHub, 2026. URL: https://github.com/sunflower3-collab/AgentFlowAttack

## Security notice

This repository is intended for education and research only. All attacks were run on an isolated testbed with synthetic data. Do not use them against real systems without the permission of their owners.
