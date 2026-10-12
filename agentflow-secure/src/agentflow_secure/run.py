"""Live swarm run: python -m agentflow_secure.run <swarm.json> --config configs/spike.json --live

Writes <stand>/runs/<series>/<timestamp>_<swarm>/journal.jsonl and result.json.
Requires OPENAI_API_KEY in the terminal session.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .conductor import run_swarm
from .controls import single_agent_variant
from .llm import OpenAIClient

STAND_DIR = Path(__file__).resolve().parents[2]


def stand_commit():
    """Testbed commit before the run; a dirty working tree is refused (for reproducibility)."""
    def git(*args):
        out = subprocess.run(["git", "-C", str(STAND_DIR), *args], capture_output=True, text=True)
        if out.returncode != 0:
            sys.exit(f"git {' '.join(args)}: {out.stderr.strip()}")
        return out.stdout.strip()

    if git("status", "--porcelain"):
        sys.exit("Testbed working tree is dirty: commit your changes before a live run")
    return git("rev-parse", "HEAD")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("swarm")
    parser.add_argument("--config", required=True)
    parser.add_argument("--live", action="store_true", help="explicit consent to paid API calls")
    parser.add_argument("--mode", choices=["swarm", "single_agent"], default="swarm",
                        help="single_agent runs the single-agent control (configs/single_agent_control.json)")
    parser.add_argument("--seed", type=int, help="seed for a repeat; without it, the seed from the config is used")
    parser.add_argument("--series", default="adhoc", help="series name: runs are written to runs/<series>/ and scored as a folder")
    args = parser.parse_args(argv)

    if not args.live:
        sys.exit("A live run makes paid API calls: pass --live to confirm")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set in this terminal session")
    commit = stand_commit()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    swarm = json.loads(Path(args.swarm).read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else config.get("seed")
    control_file = STAND_DIR / "configs" / "single_agent_control.json"
    if args.mode == "single_agent":
        swarm = single_agent_variant(swarm, json.loads(control_file.read_text(encoding="utf-8"))["agent"])

    import openai

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(swarm.get("name", "swarm")))
    series = re.sub(r"[^A-Za-z0-9_-]", "_", args.series)
    out_dir = STAND_DIR / "runs" / series / f"{stamp}_{name}_{args.mode}_s{seed}"
    out_dir.mkdir(parents=True)
    llm = OpenAIClient(config["model"], temperature=config["temperature"], seed=seed,
                       max_completion_tokens=config.get("max_completion_tokens"))
    result = run_swarm(swarm, llm=llm, journal_path=out_dir / "journal.jsonl")

    models = {line.get("model") for line in map(json.loads, (out_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines())
              if line.get("event") == "llm_call" and line.get("model")}
    result["run"] = {
        "stand_commit": commit,
        "mode": args.mode,
        "seed": seed,
        "seed_source": "cli" if args.seed is not None else "config",
        "series": series,
        "single_agent_control_sha256": file_sha256(control_file) if args.mode == "single_agent" else None,
        "requested_model": config["model"],
        "response_models": sorted(models),
        "model_matches": models == {config["model"]},
        "config": config,
        "config_sha256": file_sha256(args.config),
        "swarm_file": args.swarm,
        "swarm_sha256": file_sha256(args.swarm),
        "python": platform.python_version(),
        "openai": openai.__version__,
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_dir, result["status"], f"errors={result['errors']}", f"model_matches={result['run']['model_matches']}")
    sys.exit(0 if result["status"] == "completed" and result["run"]["model_matches"] else 1)


if __name__ == "__main__":
    main()
