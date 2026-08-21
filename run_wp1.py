from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def run_capture(cmd: list[str], cwd: Path, out_file: Path) -> int:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    print("\n$", " ".join(shlex.quote(x) for x in cmd))
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out_file.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    print(proc.stdout or "")
    return proc.returncode


def test_command(instance: str) -> tuple[Path, list[str]]:
    if instance != "sympy__sympy-20590":
        raise SystemExit(
            "This first WP1 controller currently has a verified trigger-test mapping only for "
            "sympy__sympy-20590. Add a generic trigger-test resolver before scaling."
        )
    repo = ROOT / "FlexFL" / "data" / "repos" / instance
    cmd = [
        "python",
        "-m",
        "pytest",
        "sympy/core/tests/test_basic.py::test_immutable",
        "-v",
    ]
    return repo, cmd


def run_condition(instance: str, condition: str) -> dict:
    repo, base_cmd = test_command(instance)
    out_dir = RESULTS / instance / condition
    out_dir.mkdir(parents=True, exist_ok=True)

    if condition == "raw":
        cmd = base_cmd
    elif condition == "rtk_static":
        rtk = os.environ.get("RTK_BIN", str(Path.home() / ".local" / "bin" / "rtk"))
        if not Path(rtk).exists():
            raise SystemExit(f"RTK not found at {rtk}. Set RTK_BIN if needed.")
        cmd = [rtk, "pytest", *base_cmd[3:]]
    else:
        raise ValueError(condition)

    output_file = out_dir / "pytest_output.txt"
    returncode = run_capture(cmd, repo, output_file)
    text = output_file.read_text(encoding="utf-8", errors="replace")

    result = {
        "instance_id": instance,
        "condition": condition,
        "command": cmd,
        "returncode": returncode,
        "characters": len(text),
        "lines": len(text.splitlines()),
        "output_file": str(output_file.relative_to(ROOT)),
    }
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def compare(instance: str, raw: dict, rtk: dict) -> dict:
    raw_chars = raw["characters"]
    rtk_chars = rtk["characters"]
    reduction = 0.0 if raw_chars == 0 else 100.0 * (raw_chars - rtk_chars) / raw_chars
    result = {
        "instance_id": instance,
        "raw_characters": raw_chars,
        "rtk_characters": rtk_chars,
        "character_reduction_percent": round(reduction, 2),
        "raw_lines": raw["lines"],
        "rtk_lines": rtk["lines"],
        "note": "This compares terminal/test output only. FlexFL RAW-vs-RTK agent ranking integration is the next step.",
    }
    out = RESULTS / instance / "comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", default="sympy__sympy-20590")
    parser.add_argument(
        "--condition",
        choices=["raw", "rtk_static", "both"],
        default="both",
    )
    args = parser.parse_args()

    if args.condition == "raw":
        print(json.dumps(run_condition(args.instance, "raw"), indent=2))
        return
    if args.condition == "rtk_static":
        print(json.dumps(run_condition(args.instance, "rtk_static"), indent=2))
        return

    raw = run_condition(args.instance, "raw")
    rtk = run_condition(args.instance, "rtk_static")
    print("\n=== COMPARISON ===")
    print(json.dumps(compare(args.instance, raw, rtk), indent=2))


if __name__ == "__main__":
    main()
