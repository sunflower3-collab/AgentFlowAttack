"""Driver for the C0 series. Calls run.py for each cell (attack x mode x seed),
applies the retry rule (an API error moves the run folder to _failed and retries the same seed and mode),
tracks the cost and stops if the projection or the actual spend exceeds the ceiling.

Run it from a git clone with the testbed installed (see the repository README). Paths are relative to this file.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAND = ROOT / "agentflow-secure"
ATTACKS = ROOT / "attacks" / "2026-10-10-C0-baseline"
SERIES = "C0-rerun"
CEILING_USD = 0.20  # cost ceiling
STOP_ACTUAL_USD = 0.12  # stop and report if the actual spend exceeds this
PLANNED = 100
API_ERRORS = ("RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError", "APIStatusError", "APIError")
PY = STAND / ".venv" / "Scripts" / "python.exe"
PRICES = json.loads((STAND / "configs" / "spike.json").read_text(encoding="utf-8"))["prices_usd_per_1m_tokens"]
SERIES_DIR = STAND / "runs" / SERIES


def cost_of(journal):
    total = 0.0
    for line in journal.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        u = r.get("usage") or {}
        if r.get("event") != "llm_call" or not u:
            continue
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        total += ((u.get("prompt_tokens", 0) - cached) * PRICES["input"] + cached * PRICES["cached_input"]
                  + u.get("completion_tokens", 0) * PRICES["output"]) / 1e6
    return total


def spent():
    return sum(cost_of(j) for j in SERIES_DIR.rglob("journal.jsonl")) if SERIES_DIR.exists() else 0.0


def api_failed(run_dir):
    res = run_dir / "result.json"
    if not res.exists():
        return True
    result = json.loads(res.read_text(encoding="utf-8"))
    return any((a["result"].get("error") or "").startswith(API_ERRORS) for a in result["final_result"].values())


def existing_cells():
    cells, costs = set(), {"swarm": [], "single_agent": []}
    if SERIES_DIR.exists():
        for d in SERIES_DIR.iterdir():
            if d.name == "_failed" or not (d / "result.json").exists():
                continue
            r = json.loads((d / "result.json").read_text(encoding="utf-8"))
            cells.add((r["swarm"], r["run"]["mode"], r["run"]["seed"]))
            costs[r["run"]["mode"]].append(cost_of(d / "journal.jsonl"))
    return cells, costs


def main():
    files = sorted(ATTACKS.glob("A0[0-9]_*.json"))
    done_cells, _ = existing_cells()
    print(f"cells already done: {len(done_cells)}", flush=True)
    for mode in ("swarm", "single_agent"):
        for f in files:
            for seed in range(1, 6):
                if (json.loads(f.read_text(encoding="utf-8"))["name"], mode, seed) in done_cells:
                    continue
                for attempt in range(1, 4):
                    before = set(SERIES_DIR.iterdir()) if SERIES_DIR.exists() else set()
                    proc = subprocess.run([str(PY), "-m", "agentflow_secure.run", str(f), "--config", "configs/spike.json",
                                           "--live", "--series", SERIES, "--mode", mode, "--seed", str(seed)],
                                          cwd=STAND, env={**__import__("os").environ, "PYTHONPATH": "src"},
                                          capture_output=True, text=True, encoding="utf-8", errors="replace")
                    new = [d for d in SERIES_DIR.iterdir() if d not in before and d.name != "_failed"] if SERIES_DIR.exists() else []
                    run_dir = new[0] if new else None
                    if run_dir and not api_failed(run_dir):
                        break
                    print(f"API/crash: {f.stem} {mode} s{seed} attempt {attempt}: {proc.stdout.strip()[-200:]} {proc.stderr.strip()[-300:]}", flush=True)
                    if run_dir:
                        (SERIES_DIR / "_failed").mkdir(exist_ok=True)
                        shutil.move(str(run_dir), str(SERIES_DIR / "_failed" / run_dir.name))
                    if attempt == 3:
                        print(f"STOP: 3 failed attempts for {f.stem} {mode} s{seed}", flush=True)
                        sys.exit(2)
                cells, costs = existing_cells()
                total = spent()
                avg = {m: (sum(c) / len(c) if c else {"swarm": 0.00126, "single_agent": 0.0003}[m]) for m, c in costs.items()}
                remaining = {m: 50 - len(c) for m, c in costs.items()}
                projected = total + sum(remaining[m] * avg[m] for m in avg)
                print(f"{len(cells):3d}/{PLANNED} {f.stem} {mode} s{seed}: spent ${total:.5f}, projection ${projected:.4f}", flush=True)
                if total > STOP_ACTUAL_USD or projected > CEILING_USD:
                    print(f"STOP by cost: spent ${total:.5f}, projection ${projected:.4f}", flush=True)
                    sys.exit(3)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
