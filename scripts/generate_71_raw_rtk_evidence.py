from pathlib import Path
import subprocess
import json
import ast
import re
import csv
import os
import shutil
import sys
import time

PROJECT = Path.home() / "FlexFL_SWEBench_WP1"
DATA = PROJECT / "FlexFL" / "data"
RESULTS = PROJECT / "results"

BUG_LIST = PROJECT / "configs" / "chunks" / "all_71_fl_ready.txt"

TEST_PYTHON = (
    Path.home()
    / "miniconda3"
    / "envs"
    / "flexfl-sympy38"
    / "bin"
    / "python"
)

RTK = shutil.which("rtk") or str(Path.home() / ".local" / "bin" / "rtk")

SCRATCH = Path("/scratch/parbab/FlexFL_SWEBench_WP1")
RUNNERS = SCRATCH / "evidence_runners"
TMPDIR = SCRATCH / "tmp"
CACHE = SCRATCH / "cache"

RUNNERS.mkdir(parents=True, exist_ok=True)
TMPDIR.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

env = os.environ.copy()
env["TMPDIR"] = str(TMPDIR)
env["TMP"] = str(TMPDIR)
env["TEMP"] = str(TMPDIR)
env["XDG_CACHE_HOME"] = str(CACHE)

bugs = [
    x.strip()
    for x in BUG_LIST.read_text().splitlines()
    if x.strip()
]

print("=" * 75, flush=True)
print("71-BUG RAW / RTK TERMINAL EVIDENCE GENERATION", flush=True)
print(f"Total bugs: {len(bugs)}", flush=True)
print(f"RTK: {RTK}", flush=True)
print(f"Test Python: {TEST_PYTHON}", flush=True)
print("=" * 75, flush=True)


def load_trigger_tests(path):
    text = path.read_text(encoding="utf-8").strip()

    obj = None

    try:
        obj = json.loads(text)
    except Exception:
        try:
            obj = ast.literal_eval(text)
        except Exception:
            obj = [x.strip() for x in text.splitlines() if x.strip()]

    # Some files can contain a JSON string that itself encodes a list.
    if isinstance(obj, str):
        try:
            obj2 = json.loads(obj)
            obj = obj2
        except Exception:
            obj = [obj]

    if not isinstance(obj, list):
        obj = [obj]

    return [str(x).strip() for x in obj if str(x).strip()]


def test_name_from_trigger(trigger):
    node = trigger.split("::")[-1]
    node = node.split("[", 1)[0]
    return node.strip()


def explicit_path_from_trigger(trigger):
    if "::" in trigger:
        part = trigger.split("::")[0]
        if part.endswith(".py"):
            return part
    return None


def files_from_test_patch(instance_dir):
    patch = instance_dir / "test_patch.diff"

    if not patch.exists():
        return []

    files = []

    for line in patch.read_text(
        encoding="utf-8",
        errors="replace"
    ).splitlines():

        if line.startswith("+++ b/"):
            p = line[len("+++ b/"):].strip()

            if p.endswith(".py"):
                files.append(p)

    # Prefer actual test files.
    test_files = [
        x for x in files
        if "/tests/" in x or Path(x).name.startswith("test_")
    ]

    return list(dict.fromkeys(test_files or files))


def resolve_test(repo, instance_dir, trigger):
    explicit = explicit_path_from_trigger(trigger)

    if explicit and (repo / explicit).exists():
        return explicit

    name = test_name_from_trigger(trigger)
    candidates = files_from_test_patch(instance_dir)

    # First search files touched by SWE-bench test_patch.
    for rel in candidates:
        path = repo / rel

        if not path.exists():
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except Exception:
            continue

        if re.search(
            rf"^\s*def\s+{re.escape(name)}\s*\(",
            text,
            flags=re.MULTILINE,
        ):
            return rel

    # A substring match is still useful for decorated/class tests.
    for rel in candidates:
        path = repo / rel

        if not path.exists():
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except Exception:
            continue

        if name in text:
            return rel

    # Usually SWE-bench changes only one test file.
    if len(candidates) == 1 and (repo / candidates[0]).exists():
        return candidates[0]

    # Fallback search in test files.
    for path in repo.rglob("test_*.py"):
        if ".git" in path.parts:
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except Exception:
            continue

        if re.search(
            rf"^\s*def\s+{re.escape(name)}\s*\(",
            text,
            flags=re.MULTILINE,
        ):
            return str(path.relative_to(repo))

    return None


def shell_quote(s):
    import shlex
    return shlex.quote(str(s))


rows = []
valid = 0
invalid = 0

for i, bug in enumerate(bugs, 1):

    print("\n" + "#" * 75, flush=True)
    print(f"[{i}/{len(bugs)}] {bug}", flush=True)
    print("#" * 75, flush=True)

    repo = DATA / "repos" / bug
    instance_dir = DATA / "instances" / bug
    trigger_file = (
        DATA
        / "input"
        / "trigger_tests"
        / "SWEbench"
        / f"{bug}.txt"
    )

    raw_file = RESULTS / bug / "raw" / "pytest_output.txt"
    rtk_file = RESULTS / bug / "rtk_static" / "pytest_output.txt"
    manifest_file = RESULTS / bug / "evidence_manifest.json"

    raw_file.parent.mkdir(parents=True, exist_ok=True)
    rtk_file.parent.mkdir(parents=True, exist_ok=True)

    if not repo.exists():
        print("ERROR: repository missing", flush=True)
        rows.append([
            bug, 0, 0, 0, 0, 0, "REPO_MISSING"
        ])
        invalid += 1
        continue

    if not trigger_file.exists():
        print("ERROR: trigger test file missing", flush=True)
        rows.append([
            bug, 0, 0, 0, 0, 0, "TRIGGER_MISSING"
        ])
        invalid += 1
        continue

    triggers = load_trigger_tests(trigger_file)

    print("Trigger tests:", triggers, flush=True)

    resolved = []

    for trigger in triggers:
        test_name = test_name_from_trigger(trigger)
        test_path = resolve_test(
            repo,
            instance_dir,
            trigger
        )

        print(
            f"  {test_name} -> {test_path or 'NOT FOUND'}",
            flush=True,
        )

        if test_path:
            resolved.append(
                {
                    "trigger": trigger,
                    "name": test_name,
                    "path": test_path,
                }
            )

    if not resolved:
        print("ERROR: no trigger tests resolved", flush=True)

        rows.append([
            bug,
            len(triggers),
            0,
            0,
            0,
            0,
            "NO_TEST_RESOLVED",
        ])

        invalid += 1
        continue

    runner = RUNNERS / f"{bug}.sh"

    lines = [
        "#!/usr/bin/env bash",
        "set +e",
        f"cd {shell_quote(repo)}",
        "",
    ]

    for item in resolved:
        lines += [
            'echo',
            f'echo "===== FAIL_TO_PASS: {item["name"]} ====="',
            (
                f"{shell_quote(TEST_PYTHON)} bin/test "
                f"{shell_quote(item['path'])} "
                f"-k {shell_quote(item['name'])} "
                "--no-subprocess --no-colors"
            ),
            'RC=$?',
            'echo "===== TEST EXIT CODE: $RC ====="',
            "",
        ]

    runner.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    runner.chmod(0o755)

    manifest_file.write_text(
        json.dumps(
            {
                "instance_id": bug,
                "trigger_tests": triggers,
                "resolved_tests": resolved,
                "raw_command": [
                    "bash",
                    str(runner),
                ],
                "rtk_command": [
                    str(RTK),
                    "test",
                    "bash",
                    str(runner),
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("RAW: running same failing tests...", flush=True)

    raw = subprocess.run(
        ["bash", str(runner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        env=env,
    )

    raw_file.write_text(
        raw.stdout,
        encoding="utf-8",
        errors="replace",
    )

    print("RTK: running same failing tests through RTK...", flush=True)

    rtk = subprocess.run(
        [str(RTK), "test", "bash", str(runner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        env=env,
    )

    rtk_file.write_text(
        rtk.stdout,
        encoding="utf-8",
        errors="replace",
    )

    raw_bytes = raw_file.stat().st_size
    rtk_bytes = rtk_file.stat().st_size

    reduction = (
        100.0 * (1.0 - rtk_bytes / raw_bytes)
        if raw_bytes
        else 0.0
    )

    same = raw_file.read_bytes() == rtk_file.read_bytes()

    status = "VALID"

    if not raw_bytes or not rtk_bytes:
        status = "EMPTY_OUTPUT"
    elif len(resolved) != len(triggers):
        status = "PARTIAL_TEST_RESOLUTION"
    elif same:
        status = "IDENTICAL"

    print(f"RAW bytes : {raw_bytes}", flush=True)
    print(f"RTK bytes : {rtk_bytes}", flush=True)
    print(f"Reduction : {reduction:.2f}%", flush=True)
    print(f"Identical : {same}", flush=True)
    print(f"STATUS    : {status}", flush=True)

    if status == "VALID":
        valid += 1
    else:
        invalid += 1

    rows.append([
        bug,
        len(triggers),
        len(resolved),
        raw_bytes,
        rtk_bytes,
        f"{reduction:.2f}",
        status,
    ])


summary = RESULTS / "evidence_71_summary.csv"

with summary.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "bug",
        "trigger_tests",
        "resolved_tests",
        "raw_bytes",
        "rtk_bytes",
        "reduction_pct",
        "status",
    ])

    writer.writerows(rows)


print("\n" + "=" * 75, flush=True)
print("71-BUG EVIDENCE GENERATION FINISHED", flush=True)
print("=" * 75, flush=True)
print(f"Total : {len(bugs)}", flush=True)
print(f"Valid : {valid}", flush=True)
print(f"Check : {invalid}", flush=True)
print(f"Saved : {summary}", flush=True)
print("=" * 75, flush=True)
