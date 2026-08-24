from __future__ import annotations

import ast
import csv
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path.home() / "FlexFL_SWEBench_WP1"

TEST_PYTHON = os.environ.get(
    "FLEXFL_TEST_PYTHON",
    sys.executable,
)
DATA = PROJECT / "FlexFL" / "data"

BUGS_FILE = PROJECT / "configs" / "chunks" / "test_5_sympy.txt"

METHOD_OUT = DATA / "FL_results" / "Ochiai" / "SWEbench"
SBIR_INPUT = DATA / "FL_results" / "SBIR" / "input"

METHOD_OUT.mkdir(parents=True, exist_ok=True)
SBIR_INPUT.mkdir(parents=True, exist_ok=True)


def run(cmd, cwd):
    print("$", " ".join(str(x) for x in cmd))

    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def load_meta(bug):
    p = DATA / "instances" / bug / "metadata.json"
    return json.loads(p.read_text())


def changed_test_files(bug):
    patch = DATA / "instances" / bug / "test_patch.diff"

    if not patch.exists():
        return []

    files = []

    for line in patch.read_text(errors="replace").splitlines():

        if not line.startswith("+++ b/"):
            continue

        path = line[6:].strip()

        if not path.endswith(".py"):
            continue

        if "/tests/" in path or Path(path).name.startswith("test_"):
            files.append(path)

    return list(dict.fromkeys(files))


def normalize_fail_names(meta):
    names = meta.get("FAIL_TO_PASS", [])

    if isinstance(names, str):
        try:
            names = json.loads(names)
        except Exception:
            names = [names]

    return [str(x).strip() for x in names if str(x).strip()]


def collect_nodes(repo, test_file):
    p = run(
        [
            TEST_PYTHON,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            test_file,
        ],
        repo,
    )

    nodes = []

    for line in p.stdout.splitlines():
        line = line.strip()

        if "::" not in line:
            continue

        if line.startswith(test_file):
            nodes.append(line)

    return nodes


def discover_actual_failing_tests(repo, bug):
    """
    Try three levels:

    1. Match FAIL_TO_PASS names to collected pytest nodes.
    2. If names do not match, actually run the changed test file(s)
       and parse pytest's FAILED node IDs.
    3. As a last resort, run changed test files themselves.
    """

    meta = load_meta(bug)
    fail_names = normalize_fail_names(meta)
    test_files = changed_test_files(bug)

    print("FAIL_TO_PASS metadata:", fail_names)
    print("Changed test files:", test_files)

    # --------------------------------------------------------
    # 1. Collect nodes and match names
    # --------------------------------------------------------

    all_nodes = []

    for test_file in test_files:
        all_nodes.extend(collect_nodes(repo, test_file))

    exact = []

    for node in all_nodes:
        tail = node.split("::")[-1]

        for name in fail_names:
            if tail == name or tail.startswith(name + "["):
                exact.append(node)

    exact = list(dict.fromkeys(exact))

    if exact:
        print("Resolved failing nodes directly:")
        for x in exact:
            print(" ", x)
        return exact, all_nodes

    # --------------------------------------------------------
    # 2. Run changed test files and inspect real failures
    # --------------------------------------------------------

    discovered = []

    for test_file in test_files:

        print("Running test file to discover actual failures:", test_file)

        p = run(
            [
                TEST_PYTHON,
                "-m",
                "pytest",
                "-q",
                test_file,
            ],
            repo,
        )

        for line in p.stdout.splitlines():
            line = line.strip()

            # pytest summary:
            # FAILED path/to/test.py::test_name - ...
            m = re.search(r"FAILED\s+([^\s]+::[^\s]+)", line)

            if m:
                node = m.group(1).strip()
                discovered.append(node)

    discovered = list(dict.fromkeys(discovered))

    if discovered:
        print("Discovered failing tests from pytest:")
        for x in discovered:
            print(" ", x)
        return discovered, all_nodes

    # --------------------------------------------------------
    # 3. Last fallback
    # --------------------------------------------------------

    print("WARNING: could not identify exact failing nodes.")
    print("Falling back to changed test files.")

    return test_files, all_nodes


def select_passing_tests(all_nodes, fail_nodes, max_pass=20):
    fail_set = set(fail_nodes)

    candidates = [
        node
        for node in all_nodes
        if node not in fail_set
    ]

    return candidates[:max_pass]


def coverage_json(repo, node, outfile):
    outfile.parent.mkdir(parents=True, exist_ok=True)

    # Remove previous .coverage DB so each test is independent.
    run(
        [
            TEST_PYTHON,
            "-m",
            "coverage",
            "erase",
        ],
        repo,
    )

    p = run(
        [
            TEST_PYTHON,
            "-m",
            "coverage",
            "run",
            "--branch",
            "-m",
            "pytest",
            "-q",
            node,
        ],
        repo,
    )

    # Pytest 0 = pass, 1 = real test failure.
    # Other codes indicate collection/environment/internal problems.
    print(p.stdout[-3000:])

    bad_markers = [
        "ImportError while loading conftest",
        "ERROR collecting",
        "Interrupted: 1 error",
        "INTERNALERROR",
        "collected 0 items",
    ]

    if p.returncode not in (0, 1) or any(
        marker in p.stdout for marker in bad_markers
    ):
        raise RuntimeError(
            f"Invalid pytest execution for {node}: "
            f"exit={p.returncode}"
        )

    j = run(
        [
            TEST_PYTHON,
            "-m",
            "coverage",
            "json",
            "-o",
            str(outfile),
        ],
        repo,
    )

    if j.returncode != 0 or not outfile.exists():
        print(j.stdout)
        raise RuntimeError(
            f"Could not create coverage JSON for {node}"
        )


def coverage_map(path):
    """
    Coverage.py typically stores paths relative to repository cwd,
    e.g. 'sympy/core/basic.py'.

    Keep these paths repository-relative instead of Path.resolve()
    against the outer FlexFL project.
    """

    data = json.loads(path.read_text())

    result = {}

    for file_name, info in data.get("files", {}).items():

        key = file_name.replace("\\", "/")

        # Remove leading ./ if present
        if key.startswith("./"):
            key = key[2:]

        result[key] = set(
            info.get("executed_lines", [])
        )

    return result


def module_name(path):
    path = path.replace("\\", "/")

    if path.endswith(".py"):
        path = path[:-3]

    return path.replace("/", ".")


def extract_functions(repo):
    functions = []

    for path in repo.rglob("*.py"):

        rel = path.relative_to(repo)
        rel_str = str(rel).replace("\\", "/")

        if "/tests/" in rel_str:
            continue

        if rel.name.startswith("test_"):
            continue

        try:
            source = path.read_text(errors="replace")
            tree = ast.parse(source)
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

            functions.append(
                {
                    "file": rel_str,
                    "start": node.lineno,
                    "end": getattr(
                        node,
                        "end_lineno",
                        node.lineno,
                    ),
                    "method":
                        module_name(rel_str)
                        + "."
                        + ".".join(names)
                        + "()",
                }
            )

    return functions


def valid_existing(method_file, stmt_file):
    if not method_file.exists() or not stmt_file.exists():
        return False

    method_lines = sum(1 for _ in method_file.open())
    stmt_lines = sum(1 for _ in stmt_file.open())

    # Header + at least one result
    return method_lines > 1 and stmt_lines > 1


def score_bug(bug):
    print("\n" + "=" * 90)
    print("OCHIAI:", bug)
    print("=" * 90)

    repo = DATA / "repos" / bug

    out_method = (
        METHOD_OUT
        / f"{bug}_method-susps.csv"
    )

    sbir_dir = SBIR_INPUT / bug
    sbir_dir.mkdir(parents=True, exist_ok=True)

    out_stmt = (
        sbir_dir
        / "sbfl_stmt-susps.txt"
    )

    # --------------------------------------------------------
    # Do NOT repeat valid bugs
    # --------------------------------------------------------

    if valid_existing(out_method, out_stmt):
        print("SKIP: valid Ochiai result already exists")
        return True

    # Remove invalid zero-row files.
    out_method.unlink(missing_ok=True)
    out_stmt.unlink(missing_ok=True)

    # --------------------------------------------------------
    # Identify tests
    # --------------------------------------------------------

    fail_nodes, all_nodes = discover_actual_failing_tests(
        repo,
        bug,
    )

    if not fail_nodes:
        raise RuntimeError(
            "No failing tests could be identified"
        )

    pass_nodes = select_passing_tests(
        all_nodes,
        fail_nodes,
        max_pass=20,
    )

    print("\nFail tests:")
    for x in fail_nodes:
        print(" FAIL:", x)

    print("\nSelected passing tests:", len(pass_nodes))

    for x in pass_nodes:
        print(" PASS:", x)

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    work = PROJECT / "results" / bug / "coverage"
    work.mkdir(parents=True, exist_ok=True)

    # Remove old broken coverage files
    for x in work.glob("FAIL_*.json"):
        x.unlink()

    for x in work.glob("PASS_*.json"):
        x.unlink()

    fail_covs = []
    pass_covs = []

    for i, node in enumerate(fail_nodes):

        out = work / f"FAIL_{i}.json"

        coverage_json(
            repo,
            node,
            out,
        )

        fail_covs.append(
            coverage_map(out)
        )

    for i, node in enumerate(pass_nodes):

        out = work / f"PASS_{i}.json"

        try:
            coverage_json(
                repo,
                node,
                out,
            )

            pass_covs.append(
                coverage_map(out)
            )

        except Exception as exc:
            print(
                "Passing-test coverage failed:",
                node,
                exc,
            )

    if not fail_covs:
        raise RuntimeError(
            "No failing coverage data"
        )

    # --------------------------------------------------------
    # Ochiai statement scores
    # --------------------------------------------------------

    total_fail = len(fail_covs)

    source_files = set()

    for cov in fail_covs:
        source_files.update(cov.keys())

    for cov in pass_covs:
        source_files.update(cov.keys())

    statement_rows = []

    for rel in sorted(source_files):

        rel = rel.replace("\\", "/")

        if not rel.endswith(".py"):
            continue

        if "/tests/" in rel:
            continue

        if Path(rel).name.startswith("test_"):
            continue

        fail_sets = [
            cov.get(rel, set())
            for cov in fail_covs
        ]

        pass_sets = [
            cov.get(rel, set())
            for cov in pass_covs
        ]

        candidate_lines = set()

        for lines in fail_sets:
            candidate_lines.update(lines)

        for line in candidate_lines:

            ef = sum(
                line in lines
                for lines in fail_sets
            )

            ep = sum(
                line in lines
                for lines in pass_sets
            )

            if ef == 0:
                continue

            denominator = math.sqrt(
                total_fail * (ef + ep)
            )

            score = (
                ef / denominator
                if denominator
                else 0.0
            )

            statement_rows.append(
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

    statement_rows.sort(
        key=lambda x: (
            -x["score"],
            x["statement"],
        )
    )

    if not statement_rows:
        raise RuntimeError(
            "Coverage existed, but no source statements "
            "were mapped. Check coverage paths."
        )

    # --------------------------------------------------------
    # Save statement ranking for SBIR
    # --------------------------------------------------------

    with out_stmt.open("w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "Statement",
                "Suspiciousness",
            ]
        )

        for row in statement_rows:
            writer.writerow(
                [
                    row["statement"],
                    f'{row["score"]:.12f}',
                ]
            )

    # --------------------------------------------------------
    # Convert statements to methods
    # --------------------------------------------------------

    functions = extract_functions(repo)

    by_file = {}

    for fn in functions:
        by_file.setdefault(
            fn["file"],
            [],
        ).append(fn)

    method_scores = {}

    for row in statement_rows:

        rel = row["file"]
        line = row["line"]

        candidates = [
            fn
            for fn in by_file.get(rel, [])
            if fn["start"] < line <= fn["end"]
        ]

        if not candidates:
            continue

        # Innermost/smallest containing function
        fn = min(
            candidates,
            key=lambda x: (
                x["end"] - x["start"],
                -x["start"],
            ),
        )

        method = fn["method"]

        previous = method_scores.get(method)

        candidate = {
            "Method": method,
            "Suspiciousness": row["score"],
            "ef": row["ef"],
            "ep": row["ep"],
        }

        if (
            previous is None
            or candidate["Suspiciousness"]
            > previous["Suspiciousness"]
        ):
            method_scores[method] = candidate

    ranked = sorted(
        method_scores.values(),
        key=lambda x: (
            -x["Suspiciousness"],
            x["Method"],
        ),
    )

    if not ranked:
        raise RuntimeError(
            "Statements were produced but no methods "
            "could be mapped."
        )

    with out_method.open("w", newline="") as f:

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

        for row in ranked:
            writer.writerow(row)

    print()
    print("SUCCESS")
    print("Methods:", len(ranked))
    print("Statements:", len(statement_rows))
    print("Method file:", out_method)
    print("Statement file:", out_stmt)

    print("\nTop 5 methods:")

    for row in ranked[:5]:
        print(
            row["Method"],
            row["Suspiciousness"],
            "ef=",
            row["ef"],
            "ep=",
            row["ep"],
        )

    return True


def main():

    bugs = [
        x.strip()
        for x in BUGS_FILE.read_text().splitlines()
        if x.strip()
    ]

    failures = []

    for bug in bugs:

        try:
            score_bug(bug)

        except Exception as exc:

            print()
            print("FAILED:", bug)
            print(repr(exc))

            failures.append(
                (bug, str(exc))
            )

    print("\n" + "=" * 90)
    print("FINAL OCHIAI SUMMARY")
    print("=" * 90)

    for bug in bugs:

        method_file = (
            METHOD_OUT
            / f"{bug}_method-susps.csv"
        )

        stmt_file = (
            SBIR_INPUT
            / bug
            / "sbfl_stmt-susps.txt"
        )

        valid = valid_existing(
            method_file,
            stmt_file,
        )

        m = (
            max(
                0,
                sum(1 for _ in method_file.open()) - 1,
            )
            if method_file.exists()
            else 0
        )

        s = (
            max(
                0,
                sum(1 for _ in stmt_file.open()) - 1,
            )
            if stmt_file.exists()
            else 0
        )

        print(
            f"{bug:28} "
            f"methods={m:<6} "
            f"statements={s:<7} "
            f"{'VALID' if valid else 'INVALID'}"
        )

    if failures:
        print("\nFailures:")
        for bug, error in failures:
            print(bug, error)


if __name__ == "__main__":
    main()
