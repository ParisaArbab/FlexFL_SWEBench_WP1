from __future__ import annotations

import ast
import csv
import math
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

PROJECT = Path.home() / "FlexFL_SWEBench_WP1"
DATA = PROJECT / "FlexFL" / "data"
BUG_LIST = PROJECT / "configs" / "chunks" / "test_5_sympy.txt"

SBIR_ROOT = DATA / "FL_results" / "SBIR"
SBIR_INPUT = SBIR_ROOT / "input"
SBIR_RAW = SBIR_ROOT / "raw"
SBIR_OUT = SBIR_ROOT / "SWEbench"

RAFL_RUNTIME = Path.home() / "rafl_runtime"
JDK = Path.home() / "jdk17"

for p in (SBIR_INPUT, SBIR_RAW, SBIR_OUT):
    p.mkdir(parents=True, exist_ok=True)

STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has",
    "have", "he", "her", "here", "how", "i", "if", "in", "into", "is",
    "it", "its", "may", "more", "not", "of", "on", "or", "our", "out",
    "should", "so", "some", "than", "that", "the", "their", "then",
    "there", "these", "this", "to", "up", "use", "using", "was", "we",
    "were", "what", "when", "where", "which", "will", "with", "would",
    "you", "your", "python", "sympy", "test", "tests", "issue", "error",
}


def run(cmd, cwd=None, env=None, check=False):
    print("$", " ".join(str(x) for x in cmd), flush=True)
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.stdout:
        print(p.stdout[-5000:], flush=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}")
    return p


def tokenize(text: str) -> list[str]:
    # Split normal words, snake_case, and simple camelCase identifiers.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
    out: list[str] = []
    for token in raw:
        for part in token.split("_"):
            if len(part) >= 2 and part not in STOP:
                out.append(part)
    return out


def module_name(rel: str) -> str:
    rel = rel.replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def implementation_files(repo: Path):
    for path in repo.rglob("*.py"):
        rel = str(path.relative_to(repo)).replace("\\", "/")
        if "/tests/" in rel or Path(rel).name.startswith("test_"):
            continue
        if Path(rel).name == "conftest.py":
            continue
        yield path, rel


def make_irfl(bug: str, repo: Path, out_file: Path) -> int:
    problem = (DATA / "instances" / bug / "problem_statement.md").read_text(
        encoding="utf-8", errors="replace"
    )
    query = Counter(tokenize(problem))
    if not query:
        raise RuntimeError(f"empty IR query for {bug}")

    docs: list[tuple[str, int, Counter[str]]] = []
    df: Counter[str] = Counter()

    for path, rel in implementation_files(repo):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        mod = module_name(rel)
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            counts = Counter(tokenize(stripped))
            if not counts:
                continue
            docs.append((mod, lineno, counts))
            for term in counts:
                df[term] += 1

    n = max(1, len(docs))
    scored: list[tuple[str, float]] = []
    for mod, lineno, counts in docs:
        score = 0.0
        for term, qtf in query.items():
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log((n + 1.0) / (df.get(term, 0) + 1.0)) + 1.0
            score += qtf * tf * idf
        scored.append((f"{mod}#{lineno}", score))

    scored.sort(key=lambda x: (-x[1], x[0]))
    max_score = scored[0][1] if scored else 0.0

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Statement", "Suspiciousness"])
        for stmt, score in scored:
            normalized = score / max_score if max_score > 0 else 0.0
            w.writerow([stmt, f"{normalized:.12f}"])

    return len(scored)


def find_java() -> Path:
    candidate = JDK / "bin" / "java"
    if candidate.exists():
        return candidate
    found = shutil.which("java")
    if found:
        return Path(found)
    raise RuntimeError("java not found")


def find_r_home() -> str:
    r = shutil.which("R")
    if not r:
        raise RuntimeError("R not found. Activate flexfl-swebench first.")
    p = run([r, "RHOME"])
    if p.returncode != 0:
        raise RuntimeError("could not determine R_HOME")
    # R may print warnings before the actual path. Pick the last absolute path.
    lines = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith("/")]
    if not lines:
        raise RuntimeError("RHOME returned no path")
    return lines[-1]


def build_rafl_env() -> tuple[dict[str, str], str]:
    if not RAFL_RUNTIME.exists():
        raise RuntimeError(f"RAFL runtime missing: {RAFL_RUNTIME}")

    r_home = find_r_home()
    env = os.environ.copy()
    env["R_HOME"] = r_home

    class_entries = [str(RAFL_RUNTIME)]
    class_entries += [str(p) for p in RAFL_RUNTIME.rglob("*.jar")]

    # Dependencies used successfully by the pilot.
    log4j = Path.home() / ".m2/repository/log4j/log4j/1.2.17/log4j-1.2.17.jar"
    if log4j.exists():
        class_entries.append(str(log4j))

    rjava = Path(r_home) / "library" / "rJava" / "jri"
    if not rjava.exists():
        # conda layouts sometimes keep the library under $CONDA_PREFIX/lib/R/library.
        conda = Path(os.environ.get("CONDA_PREFIX", ""))
        alt = conda / "lib/R/library/rJava/jri"
        if alt.exists():
            rjava = alt
    if rjava.exists():
        for jar in rjava.glob("*.jar"):
            class_entries.append(str(jar))

    ld = [str(Path(r_home) / "lib")]
    if rjava.exists():
        ld.append(str(rjava))
    if env.get("LD_LIBRARY_PATH"):
        ld.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(ld)

    return env, os.pathsep.join(dict.fromkeys(class_entries))


def ensure_rafl_settings():
    settings = RAFL_RUNTIME / "rafl.settings"
    settings.write_text(
        f"root_directory={SBIR_RAW.resolve()}\n",
        encoding="utf-8",
    )
    return settings


def run_rafl(bug: str, irfl: Path, sbfl: Path) -> Path:
    number = bug.rsplit("-", 1)[-1]
    defect = f"Sympy_{number}"

    env, cp = build_rafl_env()
    ensure_rafl_settings()

    java = find_java()
    cmd = [
        java,
        "-cp",
        cp,
        "main.Rafl",
        defect,
        "2",
        irfl.resolve(),
        sbfl.resolve(),
        "1",
        "10000",
    ]
    p = run(cmd, cwd=RAFL_RUNTIME, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"RAFL failed for {bug} with exit={p.returncode}")

    expected = SBIR_RAW / "sbir_seed1" / "sympy" / number / "stmt-susps.txt"
    if expected.exists():
        return expected

    # Fall back to locating the generated file in case RAFL capitalization differs.
    candidates = list((SBIR_RAW / "sbir_seed1").rglob(f"*/{number}/stmt-susps.txt"))
    if candidates:
        return candidates[0]
    raise RuntimeError(f"RAFL output not found for {bug}")


def extract_methods(repo: Path):
    methods = []
    for path, rel in implementation_files(repo):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = [node.name]
            parent = parents.get(node)
            while parent is not None:
                if isinstance(parent, ast.ClassDef):
                    names.append(parent.name)
                parent = parents.get(parent)
            names.reverse()
            methods.append({
                "module": module_name(rel),
                "start": node.lineno,
                "end": getattr(node, "end_lineno", node.lineno),
                "method": module_name(rel) + "." + ".".join(names) + "()",
            })
    return methods


def convert_to_methods(repo: Path, stmt_file: Path, out_file: Path) -> int:
    methods = extract_methods(repo)
    by_module: dict[str, list[dict]] = {}
    for m in methods:
        by_module.setdefault(m["module"], []).append(m)

    ranked: list[tuple[str, float]] = []
    seen = set()
    with stmt_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stmt = row.get("Statement", "")
            if "#" not in stmt:
                continue
            mod, line_s = stmt.rsplit("#", 1)
            try:
                line = int(line_s)
            except ValueError:
                continue
            candidates = [
                m for m in by_module.get(mod, [])
                if m["start"] <= line <= m["end"]
            ]
            if not candidates:
                continue
            chosen = min(candidates, key=lambda m: (m["end"] - m["start"], -m["start"]))
            name = chosen["method"]
            if name in seen:
                continue
            seen.add(name)
            try:
                score = float(row.get("Suspiciousness", 0.0))
            except Exception:
                score = 0.0
            ranked.append((name, score))

    if not ranked:
        raise RuntimeError(f"no SBIR methods mapped from {stmt_file}")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Method", "Suspiciousness"])
        for name, score in ranked:
            w.writerow([name, score])
    return len(ranked)


def valid_result(path: Path) -> bool:
    return path.exists() and sum(1 for _ in path.open(encoding="utf-8")) > 1


def generate(bug: str):
    print("\n" + "=" * 90, flush=True)
    print("SBIR:", bug, flush=True)
    print("=" * 90, flush=True)

    out_file = SBIR_OUT / f"{bug}_method-susps.csv"
    if valid_result(out_file):
        print("SKIP: valid SBIR result already exists", flush=True)
        return

    repo = DATA / "repos" / bug
    in_dir = SBIR_INPUT / bug
    sbfl = in_dir / "sbfl_stmt-susps.txt"
    irfl = in_dir / "irfl_stmt-susps.txt"

    if not sbfl.exists() or sum(1 for _ in sbfl.open(encoding="utf-8")) <= 1:
        raise RuntimeError(f"missing/empty SBFL input: {sbfl}")

    ir_count = make_irfl(bug, repo, irfl)
    print(f"IRFL statements: {ir_count}", flush=True)

    stmt_out = run_rafl(bug, irfl, sbfl)
    count = convert_to_methods(repo, stmt_out, out_file)

    print(f"SUCCESS: {bug}", flush=True)
    print(f"SBIR methods: {count}", flush=True)
    print("Top 5:", flush=True)
    with out_file.open(encoding="utf-8") as f:
        for line in list(f)[1:6]:
            print(" ", line.rstrip(), flush=True)


def main():
    bugs = [x.strip() for x in BUG_LIST.read_text().splitlines() if x.strip()]
    failures = []
    for bug in bugs:
        try:
            generate(bug)
        except Exception as exc:
            print(f"FAILED: {bug}: {exc!r}", flush=True)
            failures.append((bug, str(exc)))

    print("\n" + "=" * 90, flush=True)
    print("5-BUG SBIR SUMMARY", flush=True)
    print("=" * 90, flush=True)
    for bug in bugs:
        p = SBIR_OUT / f"{bug}_method-susps.csv"
        rows = max(0, sum(1 for _ in p.open(encoding="utf-8")) - 1) if p.exists() else 0
        print(f"{bug:28} methods={rows:<6} {'VALID' if rows else 'FAILED'}", flush=True)

    if failures:
        print("\nFailures:", flush=True)
        for bug, err in failures:
            print(bug, err, flush=True)


if __name__ == "__main__":
    main()
