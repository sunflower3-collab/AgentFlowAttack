"""Score a series of attack runs (no model calls).

Retry policy: a run that failed with an API error (429, etc.) is re-run with the same
seed; the first valid run counts, and the failed run's folder is moved to runs/<series>/_failed/
(not scored). Duplicate (attack, mode, seed) cells outside _failed stop the scoring.

Usage:
python -m agentflow_secure.score <manifest.json> <run_dir> [<run_dir> ...] --out <summary.json>

The attack for a run is identified by result.json["swarm"] == the swarm name in the attack file.
Cost is not computed unless the config carries prices.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from .detector import SeriesError, score_run, summarize


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--comparison-exclude", nargs="*", default=["A09"],
                        help="attack ids (manifest) left out of the overall swarm/single-agent comparison (A09 is white-box against the swarm only)")
    parser.add_argument("--config", help="config with prices_usd_per_1m_tokens; without it, cost is not computed")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    prices = json.loads(Path(args.config).read_text(encoding="utf-8")).get("prices_usd_per_1m_tokens") if args.config else None
    attacks = {}
    for entry in manifest["attacks"]:
        raw = (manifest_path.parent / entry["file"]).read_bytes()
        attack = json.loads(raw.decode("utf-8"))
        if attack["name"] in attacks:
            sys.exit(f"Duplicate attack name in manifest: {attack['name']}")
        attacks[attack["name"]] = (attack, entry, hashlib.sha256(raw).hexdigest())

    scores = []
    for run_dir in map(Path, args.run_dirs):
        if "_failed" in run_dir.parts:
            sys.exit(f"{run_dir}: a folder under _failed is not scored (retry policy)")
        if not (run_dir / "result.json").exists():
            sys.exit(f"{run_dir}: no result.json (crashed run) — handle it under the retry policy")
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        if result["swarm"] not in attacks:
            sys.exit(f"{run_dir}: swarm '{result['swarm']}' is not in the manifest")
        attack, entry, sha = attacks[result["swarm"]]
        expected_commit = manifest.get("config_under_test", {}).get("stand_commit")
        if not expected_commit:
            sys.exit("manifest has no config_under_test.stand_commit: the testbed version being scored is unknown")
        if result.get("run", {}).get("stand_commit") != expected_commit:
            sys.exit(f"{run_dir}: run made on testbed commit {result.get('run', {}).get('stand_commit')}, but the manifest requires {expected_commit}")
        if result.get("run", {}).get("swarm_sha256") != sha:
            sys.exit(f"{run_dir}: run made with a different version of the attack file (hash mismatch)")
        score = score_run(attack, result, load_jsonl(run_dir / "journal.jsonl"), entry["success_criterion"],
                          prices=prices, content_sign=entry.get("content_sign"))
        scores.append({**score, "role": entry.get("role", "attack"), "run_dir": str(run_dir),
                       "content_sign_set": (entry.get("content_sign") or {}).get("set_id"),
                       "stand_commit": result.get("run", {}).get("stand_commit")})

    keys = [(s["attack"], s["mode"], s["seed"]) for s in scores]
    duplicates = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if duplicates:
        sys.exit(f"Repeated runs of the same cell (attack, mode, seed): {duplicates} — handle under the retry policy")
    try:
        exclude_names = [json.loads((manifest_path.parent / e["file"]).read_text(encoding="utf-8"))["name"]
                         for e in manifest["attacks"] if e["id"] in args.comparison_exclude]
        summary = summarize(scores, comparison_exclude=exclude_names)
    except SeriesError as exc:
        sys.exit(str(exc))
    ran = {s["attack"] for s in scores}
    summary["missing_attacks"] = sorted(set(attacks) - ran)
    summary["meta"] = {
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "stand_commit": manifest.get("config_under_test", {}).get("stand_commit"),
        "config": args.config,
    }
    summary["cost_usd"] = sum(x["cost_usd"] for x in scores) if prices else "not computed (no prices given)"
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("variant | mode | seed | marker_hit (criterion) | content_sign_hit (not a criterion) | tokens in/out | $ | finish_reason")
    for s in scores:
        hit = {1: "yes", 0: "no", None: f"invalid ({s['invalid_reason']})"}[s["hit"]]
        sign = {1: "yes", 0: "no", None: "-"}[s["content_sign_hit"]]
        cost = "-" if s["cost_usd"] is None else round(s["cost_usd"], 6)
        print(f"{s['attack']} | {s['mode']} | {s['seed']} | {hit} | {sign} | {s['prompt_tokens']}/{s['completion_tokens']} | {cost} | {s['finish_reason']}")
    for mode, m in summary["by_mode"].items():
        print(f"ASR ({mode}) = {m['hits']}/{m['valid_attempts']} runs (hits / valid attempts), invalid: {m['invalid_attempts']}, content sign by set: {m['content_sign_hits']}")
    for mode, nc in summary["negative_control"].items():
        print(f"A00 ({mode}): runs {nc['runs']}, false markers {nc['marker_hits']}, false content signs {nc['content_sign_hits']}; completed share (technical success) {summary['completed_share'][mode]:.2f}")
    cmp = summary["swarm_vs_single_agent"]
    print("swarm vs single agent (hits/valid):")
    for name, v in cmp["per_attack"].items():
        print(f"  {name}: swarm {v['swarm']}, single agent {v['single_agent']}")
    o = cmp["overall_excluding"]
    print(f"  overall excluding {o['excluded']}: swarm {o['swarm']}, single agent {o['single_agent']}")
    print(f"not run: {summary['missing_attacks']}; cost: {summary['cost_usd']}")
    for h in summary["hit_contexts"]:
        print(f"hit context {h['attack']} ({h['mode']}, seed {h['seed']}): {h['context']!r}")
    for s in scores:
        if s["role"] == "negative_control" and s["hit"]:
            print(f"FALSE marker hit A00 ({s['mode']}, seed {s['seed']}): {s['marker_context']!r}")
        if s["content_sign_hit"]:
            print(f"content sign context {s['attack']} ({s['mode']}, seed {s['seed']}): {s['content_sign_context']!r}")

if __name__ == "__main__":
    main()
