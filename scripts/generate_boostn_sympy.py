from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

PROJECT = Path.home() / "FlexFL_SWEBench_WP1"
DATA = PROJECT / "FlexFL" / "data"
BOOSTN = PROJECT / "BoostN"
BUG_LIST = PROJECT / "configs" / "chunks" / "test_5_sympy.txt"
OUT_DIR = DATA / "FL_results" / "BoostN" / "SWEbench"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAVEN = Path.home() / "apache-maven-3.9.11" / "bin" / "mvn"
JAVA_HOME = Path.home() / "jdk17"


def env_for_java() -> dict[str, str]:
    env = os.environ.copy()
    if JAVA_HOME.exists():
        env["JAVA_HOME"] = str(JAVA_HOME)
        env["PATH"] = str(JAVA_HOME / "bin") + os.pathsep + env.get("PATH", "")
    if MAVEN.exists():
        env["PATH"] = str(MAVEN.parent) + os.pathsep + env.get("PATH", "")
    return env


def mvn_cmd() -> str:
    return str(MAVEN) if MAVEN.exists() else "mvn"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("$", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        env=env_for_java(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.stdout:
        print(p.stdout[-5000:], flush=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed with exit={p.returncode}: {' '.join(map(str, cmd))}")
    return p


def clean_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def valid_result(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return sum(1 for _ in path.open(encoding="utf-8")) > 1
    except Exception:
        return False


def ensure_build() -> None:
    marker = BOOSTN / "target" / "classes" / "BoostNSift" / "BoostN.class"
    if marker.exists():
        print("BoostN already compiled.", flush=True)
        return
    run([mvn_cmd(), "clean", "install", "-q"], BOOSTN)


def prepare_inputs(bug: str) -> tuple[Path, Path]:
    raw = DATA / "input" / "buggy_program" / "SWEbench" / f"{bug}.corpusRawMethodLevelGranularity"
    mapping = DATA / "input" / "buggy_program" / "SWEbench" / f"{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity"
    report = DATA / "input" / "bug_reports" / "SWEbench" / f"{bug}.json"

    for p in (raw, mapping, report):
        if not p.exists():
            raise FileNotFoundError(p)

    work = BOOSTN / "temp_data" / bug
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    corpus_target = work / f"{bug}.corpusRawMethodLevelGranularity"
    shutil.copy2(raw, corpus_target)

    data = json.loads(report.read_text(encoding="utf-8"))
    title = clean_text(data.get("title", bug)) or bug
    desc = clean_text(data.get("description", ""))

    (work / f"{bug}_Titles.csv").write_text(title + "\n", encoding="utf-8")
    (work / f"{bug}_Desc.csv").write_text(desc + "\n", encoding="utf-8")
    (work / f"{bug}_Comm.csv").write_text("\n", encoding="utf-8")

    return work, mapping


def preprocess(work: Path, bug: str) -> None:
    # CorpusPreprocessor concatenates outputFolder directly with filenames,
    # so the trailing slash is required.
    out_folder = str(work) + "/"
    inputs = [
        work / f"{bug}.corpusRawMethodLevelGranularity",
        work / f"{bug}_Titles.csv",
        work / f"{bug}_Desc.csv",
        work / f"{bug}_Comm.csv",
    ]

    for p in inputs:
        run(
            [
                mvn_cmd(), "-q", "exec:java",
                "-Dexec.mainClass=corpusPreprocessor.MainCorpusPreprocessor",
                f"-Dexec.args={p} {out_folder}",
            ],
            BOOSTN,
        )


def execute_boostn(work: Path, bug: str) -> Path:
    run(
        [
            mvn_cmd(), "-q", "exec:java",
            "-Dexec.mainClass=BoostNSift.BoostN",
            f"-Dexec.args={work} {bug}",
        ],
        BOOSTN,
    )
    result = work / "Results.csv"
    if not result.exists() or result.stat().st_size == 0:
        raise RuntimeError(f"BoostN did not create a usable Results.csv for {bug}")
    return result


def convert(result_file: Path, mapping_file: Path, out_file: Path) -> int:
    mapping = [x.strip() for x in mapping_file.read_text(encoding="utf-8").splitlines()]
    scores: dict[int, float] = {}

    for line in result_file.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [x.strip() for x in line.split(",") if x.strip() != ""]
        i = 0
        while i + 1 < len(parts):
            try:
                method_id = int(parts[i])
                score = float(parts[i + 1])
            except ValueError:
                i += 2
                continue
            if 0 <= method_id < len(mapping):
                scores[method_id] = max(scores.get(method_id, float("-inf")), score)
            i += 2

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if not ranked:
        raise RuntimeError("No BoostN method scores could be parsed")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Method", "Suspiciousness"])
        for method_id, score in ranked:
            method = mapping[method_id].replace("$", ".")
            w.writerow([method, score])

    return len(ranked)


def generate(bug: str) -> None:
    print("\n" + "=" * 90, flush=True)
    print("BOOSTN:", bug, flush=True)
    print("=" * 90, flush=True)

    out = OUT_DIR / f"{bug}_method-susps.csv"
    if valid_result(out):
        rows = max(0, sum(1 for _ in out.open(encoding="utf-8")) - 1)
        print(f"SKIP: existing valid result with {rows} methods", flush=True)
        return

    out.unlink(missing_ok=True)
    work, mapping = prepare_inputs(bug)
    preprocess(work, bug)
    result = execute_boostn(work, bug)
    count = convert(result, mapping, out)

    print(f"SUCCESS: {bug}", flush=True)
    print(f"Ranked methods: {count}", flush=True)
    print("Top 5:", flush=True)
    with out.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            if i > 5:
                break
            print(" ", line.rstrip(), flush=True)


def main() -> None:
    bugs = [x.strip() for x in BUG_LIST.read_text().splitlines() if x.strip()]
    ensure_build()
    failures: list[tuple[str, str]] = []

    for bug in bugs:
        try:
            generate(bug)
        except Exception as e:
            print(f"FAILED: {bug}: {e!r}", flush=True)
            failures.append((bug, str(e)))

    print("\n" + "=" * 90, flush=True)
    print("5-BUG BOOSTN SUMMARY", flush=True)
    print("=" * 90, flush=True)
    for bug in bugs:
        out = OUT_DIR / f"{bug}_method-susps.csv"
        rows = max(0, sum(1 for _ in out.open(encoding="utf-8")) - 1) if out.exists() else 0
        status = "VALID" if rows > 0 else "FAILED"
        print(f"{bug:28} methods={rows:<7} {status}", flush=True)

    if failures:
        print("\nFailures:", flush=True)
        for bug, error in failures:
            print(bug, error, flush=True)


if __name__ == "__main__":
    main()
