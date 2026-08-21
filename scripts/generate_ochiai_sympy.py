from __future__ import annotations

import ast
import csv
import json
import math
import os
import re
import subprocess
from pathlib import Path

PROJECT = Path.home() / "FlexFL_SWEBench_WP1"
DATA = PROJECT / "FlexFL" / "data"

BUG_LIST = PROJECT / "configs/chunks/test_5_sympy.txt"

TEST_PYTHON = os.environ.get(
    "FLEXFL_TEST_PYTHON",
    str(Path.home() / "miniconda3/envs/flexfl-sympy38/bin/python")
)

METHOD_OUT = DATA / "FL_results" / "Ochiai" / "SWEbench"
SBIR_INPUT = DATA / "FL_results" / "SBIR" / "input"

METHOD_OUT.mkdir(parents=True, exist_ok=True)
SBIR_INPUT.mkdir(parents=True, exist_ok=True)


def run(cmd, cwd, env=None):
    print("$", " ".join(map(str, cmd)))

    return subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def repo_env(repo):
    env = os.environ.copy()

    previous = env.get("PYTHONPATH", "")

    paths = [
        str(repo),
        str(repo / "bin"),
    ]

    if previous:
        paths.append(previous)

    env["PYTHONPATH"] = os.pathsep.join(paths)

    return env


def metadata(bug):
    path = DATA / "instances" / bug / "metadata.json"
    return json.loads(path.read_text())


def normalize_list(value):
    if isinstance(value, list):
        return [str(x) for x in value]

    if isinstance(value, str):
        try:
            x = json.loads(value)
            if isinstance(x, list):
                return [str(y) for y in x]
        except Exception:
            pass

        return [value]

    return []


def apply_test_patch(bug, repo):
    patch = DATA / "instances" / bug / "test_patch.diff"

    if not patch.exists():
        print("No test patch found")
        return

    reverse = run(
        ["git", "apply", "--reverse", "--check", str(patch)],
        repo,
    )

    if reverse.returncode == 0:
        print("Test patch already applied.")
        return

    check = run(
        ["git", "apply", "--check", str(patch)],
        repo,
    )

    if check.returncode != 0:
        print(check.stdout)
        raise RuntimeError("test_patch.diff cannot be applied")

    result = run(
        ["git", "apply", str(patch)],
        repo,
    )

    if result.returncode != 0:
        print(result.stdout)
        raise RuntimeError("test_patch.diff application failed")

    print("Test patch applied.")


def changed_test_files(bug):
    patch = DATA / "instances" / bug / "test_patch.diff"

    files = []

    for line in patch.read_text(errors="replace").splitlines():

        if not line.startswith("+++ b/"):
            continue

        f = line[6:].strip()

        if f.endswith(".py") and (
            "/tests/" in f
            or Path(f).name.startswith("test_")
        ):
            files.append(f)

    return list(dict.fromkeys(files))


def added_test_names(bug):
    patch = DATA / "instances" / bug / "test_patch.diff"

    names = []

    pattern = re.compile(
        r"^\+\s*def\s+(test_[A-Za-z0-9_]+)\s*\("
    )

    for line in patch.read_text(errors="replace").splitlines():
        m = pattern.match(line)

        if m:
            names.append(m.group(1))

    return list(dict.fromkeys(names))


def parse_test_file(path):
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except Exception:
        return []

    names = []

    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            if node.name.startswith("test_"):
                names.append(node.name)

    return list(dict.fromkeys(names))


def build_test_index(repo):
    index = {}

    for path in repo.rglob("test_*.py"):

        rel = str(path.relative_to(repo)).replace("\\", "/")

        for name in parse_test_file(path):
            index.setdefault(name, []).append(rel)

    return index


def resolve_fail_tests(bug, repo, index):
    meta = metadata(bug)

    requested = normalize_list(
        meta.get("FAIL_TO_PASS", [])
    )

    changed = changed_test_files(bug)

    result = []

    for name in requested:

        locations = index.get(name, [])

        preferred = [
            x for x in locations
            if x in changed
        ]

        selected = preferred or locations

        if selected:
            result.append((selected[0], name))

    if not result:

        for name in added_test_names(bug):

            locations = index.get(name, [])

            preferred = [
                x for x in locations
                if x in changed
            ]

            selected = preferred or locations

            if selected:
                result.append((selected[0], name))

    result = list(dict.fromkeys(result))

    print("FAIL_TO_PASS metadata:", requested)
    print("Resolved failing tests:")

    for f, name in result:
        print("  ", f, name)

    if not result:
        raise RuntimeError(
            "Could not resolve FAIL_TO_PASS tests"
        )

    return result


def resolve_pass_tests(bug, repo, index, failing, limit=20):
    meta = metadata(bug)

    requested = normalize_list(
        meta.get("PASS_TO_PASS", [])
    )

    failing_set = set(failing)

    result = []

    for name in requested:

        locations = index.get(name, [])

        if not locations:
            continue

        item = (locations[0], name)

        if item in failing_set:
            continue

        if item not in result:
            result.append(item)

        if len(result) >= limit:
            break

    if len(result) < limit:

        fail_files = set(x[0] for x in failing)

        for name, locations in index.items():

            for location in locations:

                if location not in fail_files:
                    continue

                item = (location, name)

                if item in failing_set or item in result:
                    continue

                result.append(item)

                if len(result) >= limit:
                    break

            if len(result) >= limit:
                break

    return result[:limit]


def run_sympy_coverage(
    repo,
    test_file,
    test_name,
    output,
    should_fail,
):
    env = repo_env(repo)

    run(
        [TEST_PYTHON, "-m", "coverage", "erase"],
        repo,
        env,
    )

    cmd = [
        TEST_PYTHON,
        "-m",
        "coverage",
        "run",
        "--branch",
        "bin/test",
        test_file,
        "-k",
        test_name,
        "--no-subprocess",
        "--no-colors",
    ]

    result = run(cmd, repo, env)

    print(result.stdout[-2500:])

    if should_fail:
        if result.returncode != 1:
            print(
                "Expected FAIL but exit code was",
                result.returncode,
            )
            return False
    else:
        if result.returncode != 0:
            print(
                "Skipping non-passing PASS_TO_PASS:",
                test_file,
                test_name,
            )
            return False

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = run(
        [
            TEST_PYTHON,
            "-m",
            "coverage",
            "json",
            "-o",
            str(output),
        ],
        repo,
        env,
    )

    if report.returncode != 0 or not output.exists():
        print(report.stdout)
        return False

    return True


def load_coverage(path):
    data = json.loads(path.read_text())

    result = {}

    for name, info in data.get("files", {}).items():

        key = name.replace("\\", "/")

        if key.startswith("./"):
            key = key[2:]

        result[key] = set(
            info.get("executed_lines", [])
        )

    return result


def module_name(rel):
    rel = rel.replace("\\", "/")

    if rel.endswith(".py"):
        rel = rel[:-3]

    return rel.replace("/", ".")


def extract_methods(repo):
    methods = []

    for path in repo.rglob("*.py"):

        rel = str(
            path.relative_to(repo)
        ).replace("\\", "/")

        if "/tests/" in rel:
            continue

        if Path(rel).name.startswith("test_"):
            continue

        if Path(rel).name == "conftest.py":
            continue

        try:
            tree = ast.parse(
                path.read_text(errors="replace")
            )
        except Exception:
            continue

        parents = {}

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):

            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue

            names = [node.name]

            parent = parents.get(node)

            while parent is not None:

                if isinstance(parent, ast.ClassDef):
                    names.append(parent.name)

                parent = parents.get(parent)

            names.reverse()

            methods.append(
                {
                    "file": rel,
                    "start": node.lineno,
                    "end": getattr(
                        node,
                        "end_lineno",
                        node.lineno,
                    ),
                    "method":
                        module_name(rel)
                        + "."
                        + ".".join(names)
                        + "()",
                }
            )

    return methods


def valid_result(method_file, stmt_file):

    if not method_file.exists():
        return False

    if not stmt_file.exists():
        return False

    return (
        sum(1 for _ in method_file.open()) > 1
        and
        sum(1 for _ in stmt_file.open()) > 1
    )


def generate(bug):

    print()
    print("=" * 90)
    print("OCHIAI:", bug)
    print("=" * 90)

    repo = DATA / "repos" / bug

    method_file = (
        METHOD_OUT
        / f"{bug}_method-susps.csv"
    )

    sbir_dir = SBIR_INPUT / bug
    sbir_dir.mkdir(parents=True, exist_ok=True)

    stmt_file = (
        sbir_dir
        / "sbfl_stmt-susps.txt"
    )

    if valid_result(method_file, stmt_file):
        print("SKIP: valid result already exists")
        return

    method_file.unlink(missing_ok=True)
    stmt_file.unlink(missing_ok=True)

    apply_test_patch(bug, repo)

    index = build_test_index(repo)

    failing = resolve_fail_tests(
        bug,
        repo,
        index,
    )

    passing = resolve_pass_tests(
        bug,
        repo,
        index,
        failing,
        limit=20,
    )

    print("PASS_TO_PASS selected:", len(passing))

    work = (
        PROJECT
        / "results"
        / bug
        / "coverage"
    )

    work.mkdir(parents=True, exist_ok=True)

    for old in work.glob("*.json"):
        old.unlink()

    fail_cov = []
    pass_cov = []

    for i, (test_file, test_name) in enumerate(failing):

        output = work / f"FAIL_{i}.json"

        ok = run_sympy_coverage(
            repo,
            test_file,
            test_name,
            output,
            should_fail=True,
        )

        if not ok:
            raise RuntimeError(
                f"FAIL_TO_PASS did not fail: "
                f"{test_file}::{test_name}"
            )

        fail_cov.append(
            load_coverage(output)
        )

    for i, (test_file, test_name) in enumerate(passing):

        output = work / f"PASS_{i}.json"

        ok = run_sympy_coverage(
            repo,
            test_file,
            test_name,
            output,
            should_fail=False,
        )

        if ok:
            pass_cov.append(
                load_coverage(output)
            )

    print()
    print("Fail coverage runs:", len(fail_cov))
    print("Valid pass coverage runs:", len(pass_cov))

    if not fail_cov:
        raise RuntimeError("No valid failing coverage")

    total_fail = len(fail_cov)

    files = set()

    for cov in fail_cov + pass_cov:
        files.update(cov.keys())

    rows = []

    for rel in sorted(files):

        if not rel.endswith(".py"):
            continue

        if "/tests/" in rel:
            continue

        if Path(rel).name.startswith("test_"):
            continue

        if Path(rel).name == "conftest.py":
            continue

        fail_sets = [
            x.get(rel, set())
            for x in fail_cov
        ]

        pass_sets = [
            x.get(rel, set())
            for x in pass_cov
        ]

        lines = set()

        for x in fail_sets:
            lines.update(x)

        for line in lines:

            ef = sum(
                line in x
                for x in fail_sets
            )

            ep = sum(
                line in x
                for x in pass_sets
            )

            if ef == 0:
                continue

            denom = math.sqrt(
                total_fail * (ef + ep)
            )

            score = (
                ef / denom
                if denom
                else 0.0
            )

            rows.append(
                {
                    "statement":
                        f"{module_name(rel)}#{line}",
                    "score": score,
                    "file": rel,
                    "line": line,
                    "ef": ef,
                    "ep": ep,
                }
            )

    rows.sort(
        key=lambda x: (
            -x["score"],
            x["statement"],
        )
    )

    if not rows:
        raise RuntimeError(
            "No suspicious statements produced"
        )

    with stmt_file.open("w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "Statement",
                "Suspiciousness",
            ]
        )

        for x in rows:
            writer.writerow(
                [
                    x["statement"],
                    f'{x["score"]:.12f}',
                ]
            )

    methods = extract_methods(repo)

    by_file = {}

    for method in methods:
        by_file.setdefault(
            method["file"],
            []
        ).append(method)

    scores = {}

    for x in rows:

        candidates = [
            m
            for m in by_file.get(
                x["file"],
                [],
            )
            if m["start"] < x["line"] <= m["end"]
        ]

        if not candidates:
            continue

        method = min(
            candidates,
            key=lambda m: (
                m["end"] - m["start"],
                -m["start"],
            ),
        )

        name = method["method"]

        candidate = {
            "Method": name,
            "Suspiciousness": x["score"],
            "ef": x["ef"],
            "ep": x["ep"],
        }

        old = scores.get(name)

        if (
            old is None
            or candidate["Suspiciousness"]
            > old["Suspiciousness"]
        ):
            scores[name] = candidate

    ranked = sorted(
        scores.values(),
        key=lambda x: (
            -x["Suspiciousness"],
            x["Method"],
        )
    )

    if not ranked:
        raise RuntimeError(
            "No method-level ranking produced"
        )

    with method_file.open("w", newline="") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Method",
                "Suspiciousness",
                "ef",
                "ep",
            ],
        )

        writer.writeheader()
        writer.writerows(ranked)

    print()
    print("SUCCESS:", bug)
    print("Methods:", len(ranked))
    print("Statements:", len(rows))

    print("Top 5:")

    for x in ranked[:5]:
        print(
            x["Method"],
            round(x["Suspiciousness"], 6),
            "ef=",
            x["ef"],
            "ep=",
            x["ep"],
        )


def main():

    bugs = [
        x.strip()
        for x in BUG_LIST.read_text().splitlines()
        if x.strip()
    ]

    failed = []

    for bug in bugs:

        try:
            generate(bug)

        except Exception as exc:

            print()
            print("FAILED:", bug, repr(exc))

            failed.append(
                (bug, str(exc))
            )

    print()
    print("=" * 90)
    print("5-BUG OCHIAI SUMMARY")
    print("=" * 90)

    for bug in bugs:

        m = (
            METHOD_OUT
            / f"{bug}_method-susps.csv"
        )

        s = (
            SBIR_INPUT
            / bug
            / "sbfl_stmt-susps.txt"
        )

        mc = (
            max(
                0,
                sum(1 for _ in m.open()) - 1,
            )
            if m.exists()
            else 0
        )

        sc = (
            max(
                0,
                sum(1 for _ in s.open()) - 1,
            )
            if s.exists()
            else 0
        )

        status = (
            "VALID"
            if mc > 0 and sc > 0
            else "FAILED"
        )

        print(
            f"{bug:28} "
            f"methods={mc:<6} "
            f"stmts={sc:<7} "
            f"{status}"
        )

    if failed:

        print("\nFailures:")

        for bug, error in failed:
            print(bug, error)


if __name__ == "__main__":
    main()
