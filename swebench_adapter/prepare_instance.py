#!/usr/bin/env python3
"""Prepare one SWE-bench Lite bug for FlexFL without changing FlexFL logic.

This adapter is the dataset/language boundary. It downloads the SWE-bench record,
checks out the buggy base commit, stores the report/gold patch, and builds the two
method-level corpus files expected by the original FlexFL function-call layer.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
from pathlib import Path

from datasets import load_dataset


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)


def find_record(instance_id: str) -> dict:
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    for row in ds:
        if row["instance_id"] == instance_id:
            return dict(row)
    raise KeyError(f"SWE-bench Lite instance not found: {instance_id}")


def changed_python_files(patch: str) -> list[str]:
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            if path.endswith(".py") and path not in files:
                files.append(path)
    return files


def method_name(path: Path, root: Path, node: ast.AST, parents: list[str]) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts

    module_name = parts[-1]
    package = ".".join(parts[:-1])

    name = getattr(node, "name", "<unknown>")
    scope = ".".join([module_name] + parents + [name])

    return f"{package}${scope}()"


def collect_python_methods(repo: Path) -> tuple[list[str], list[str]]:
    mapping: list[str] = []
    raw: list[str] = []

    ignored = {".git", ".tox", ".venv", "venv", "build", "dist", "site-packages"}
    for path in sorted(repo.rglob("*.py")):
        if any(part in ignored for part in path.parts):
            continue

        rel_parts = path.relative_to(repo).parts

        # For the SymPy SWE-bench instance, FlexFL searches the actual
        # implementation package, not repository tooling/docs/examples.
        if not rel_parts or rel_parts[0] != "sympy":
            continue

        if "tests" in rel_parts or path.name.startswith("test_"):
            continue

        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        lines = text.splitlines()

        def walk(body: list[ast.stmt], parents: list[str]) -> None:
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = max(1, getattr(node, "lineno", 1))
                    end = getattr(node, "end_lineno", start)
                    snippet = "\n".join(lines[start - 1 : end]).strip()
                    mapping.append(method_name(path, repo, node, parents))
                    raw.append(snippet.replace("\n", "\\n"))
                elif isinstance(node, ast.ClassDef):
                    walk(node.body, parents + [node.name])

        walk(tree.body, [])
    return mapping, raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="sympy__sympy-20590")
    ap.add_argument("--out", default="FlexFL/data")
    args = ap.parse_args()

    instance = args.instance
    out = Path(args.out)
    record = find_record(instance)

    bug_dir = out / "input" / "bug_reports" / "SWEbench"
    trigger_dir = out / "input" / "trigger_tests" / "SWEbench"
    corpus_dir = out / "input" / "buggy_program" / "SWEbench"
    meta_dir = out / "instances" / instance
    repo_dir = out / "repos" / instance
    for d in (bug_dir, trigger_dir, corpus_dir, meta_dir, repo_dir.parent):
        d.mkdir(parents=True, exist_ok=True)

    bug_report = {
        "title": instance,
        "description": record.get("problem_statement", ""),
    }
    (bug_dir / f"{instance}.json").write_text(json.dumps(bug_report, indent=2), encoding="utf-8")

    fail_to_pass = record.get("FAIL_TO_PASS", "")
    if isinstance(fail_to_pass, list):
        trigger_text = "\n".join(fail_to_pass)
    else:
        trigger_text = str(fail_to_pass)
    (trigger_dir / f"{instance}.txt").write_text(trigger_text, encoding="utf-8")

    metadata = {
        "instance_id": instance,
        "repo": record["repo"],
        "base_commit": record["base_commit"],
        "changed_python_files": changed_python_files(record.get("patch", "")),
        "FAIL_TO_PASS": record.get("FAIL_TO_PASS"),
        "PASS_TO_PASS": record.get("PASS_TO_PASS"),
    }
    (meta_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (meta_dir / "problem_statement.md").write_text(record.get("problem_statement", ""), encoding="utf-8")
    (meta_dir / "gold_patch.diff").write_text(record.get("patch", ""), encoding="utf-8")
    (meta_dir / "test_patch.diff").write_text(record.get("test_patch", ""), encoding="utf-8")

    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    sh("git", "clone", "--quiet", f"https://github.com/{record['repo']}.git", str(repo_dir))
    sh("git", "checkout", "--quiet", record["base_commit"], cwd=repo_dir)

    mapping, raw = collect_python_methods(repo_dir)
    mapping_path = corpus_dir / f"{instance}.corpusMappingWithPackageSeparatorMethodLevelGranularity"
    raw_path = corpus_dir / f"{instance}.corpusRawMethodLevelGranularity"
    mapping_path.write_text("\n".join(mapping) + "\n", encoding="utf-8")
    raw_path.write_text("\n".join(raw) + "\n", encoding="utf-8")

    summary = {
        "instance_id": instance,
        "repo": record["repo"],
        "base_commit": record["base_commit"],
        "method_count": len(mapping),
        "gold_changed_python_files": metadata["changed_python_files"],
        "status": "prepared",
    }
    (meta_dir / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
