# agentflow-secure

A small, self-contained reimplementation of the AgentFlow conductor, built to test how a swarm of LLM agents reacts to prompt injection.

## What it is

AgentFlow is a no-code framework by D. Lande and L. Strashnoy: each agent's logic is written as a prompt, and a single universal conductor runs every scenario. Its formal model has four parts, D = ⟨P, S, E, M⟩ – a parser, a scheduler, an executor and a state manager (Lande & Strashnoy, *Orchestration of No-Code Agents in the AgentFlow Framework*, SSRN, 2025, DOI: [10.2139/ssrn.5381820](https://doi.org/10.2139/ssrn.5381820)).

This package reproduces that model in plain Python, using the official `openai` SDK and no orchestration framework (no LangChain, LangGraph or AutoGen). The goal is to stay close to the paper rather than to a framework's own execution model.

## How it works

- **Swarm description.** A JSON file lists the agents (role, logic, state), the execution phases and the input data. The test scenario, `tests/data/lande2025b_complex_scenario.json`, follows the four-agent example from the paper.
- **One LLM call per agent.** For each agent the conductor builds a prompt from its role, logic, state and input, sends it to the model once and stores the answer. There is no tool-calling and no security policy.
- **Phases.** Agents run phase by phase. Every agent receives the swarm's input data together with the outputs of all agents from earlier phases.
- **Not reproduced.** Building a syntax tree from the prompts, conditional edges and true parallel execution.
- **Journal.** Every run writes `journal.jsonl` (each LLM call with its prompt, answer, token counts and model fingerprint) and `result.json` to `runs/<series>/<timestamp>_<scenario>/`.
- **Scoring.** `agentflow_secure.score` reads the run folders and an attack manifest, and checks deterministically whether the final answer contains the attacker's marker string.

Source code lives in `src/agentflow_secure/`:
- `conductor.py` – the conductor;
- `llm.py` – the model client;
- `detector.py` and `score.py` – scoring;
- `controls.py` – single-agent and negative controls;
- `run.py` – command-line entry point.

## Setup

Tested with Python 3.14.4 on Windows (PowerShell).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Offline tests (no network, no API key)

The tests replace the language model with a stub, so they need neither an API key nor internet access.

```powershell
.venv\Scripts\python -m pytest -q
```

## Live run (paid)

A live run calls the OpenAI API and needs **your own** API key. Set it only for the current terminal session, not in a file. Nothing is sent to the API unless you pass `--live`.

```powershell
$env:OPENAI_API_KEY = "..."
$env:PYTHONPATH = "src"
.venv\Scripts\python -m agentflow_secure.run tests\data\lande2025b_complex_scenario.json --config configs\spike.json --series demo --live
```

The run is saved to `runs\demo\`. The model, temperature and token prices are set in `configs/spike.json` (`gpt-4o-mini-2024-07-18`, temperature 0). Options:
- `--mode single_agent` – run the same input through a single LLM call instead of the swarm;
- `--seed N` – set the sampling seed.

To repeat the full attack series and re-score saved results, see `../results/2026-10-11-C0-series/README.md`.
