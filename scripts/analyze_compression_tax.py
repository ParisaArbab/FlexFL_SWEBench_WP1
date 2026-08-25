from pathlib import Path
from collections import Counter
import csv
import json
import re
import difflib

ROOT = Path.home() / "FlexFL_SWEBench_WP1"
ANALYSIS = ROOT / "results" / "analysis"
DETAILS = ANALYSIS / "compression_tax_details"

INPUT_CSV = ANALYSIS / "71bug_raw_vs_rtk.csv"
OUT_CSV = ANALYSIS / "compression_tax_taxonomy.csv"
OUT_MD = ANALYSIS / "error_taxonomy_report.md"

DETAILS.mkdir(parents=True, exist_ok=True)


def read_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def exception_types(text):
    pattern = r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b"
    return sorted(set(re.findall(pattern, text)))


def traceback_frames(text):
    return re.findall(
        r'File "([^"]+\.py)", line (\d+)',
        text
    )


def python_refs(text):
    refs = re.findall(
        r'(?<![\w])(?:/[\w./-]+|[\w./-]+)\.py(?::\d+)?',
        text
    )

    cleaned = set()

    for r in refs:
        if "/site-packages/" in r:
            continue
        if "/miniconda" in r:
            continue
        cleaned.add(r)

    return sorted(cleaned)


def test_names(text):
    return sorted(set(re.findall(r"\btest_[A-Za-z0-9_]+\b", text)))


def assertion_lines(text):
    result = []

    for line in text.splitlines():
        s = line.strip()

        if (
            "AssertionError" in s
            or s.startswith("assert ")
            or " assert " in s
            or s.startswith("E   assert")
        ):
            result.append(s)

    return result


def failure_lines(text):
    result = []

    keywords = (
        "FAILED",
        "[FAIL]",
        "[ERROR]",
        "AssertionError",
        "IndexError",
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "RuntimeError",
        "NotImplementedError",
        "Exception",
        "Traceback",
    )

    for line in text.splitlines():
        if any(k in line for k in keywords):
            result.append(line.strip())

    return result


def useful_removed_lines(raw, rtk, limit=30):
    rtk_lines = set(x.strip() for x in rtk.splitlines())

    keywords = (
        "Error",
        "Exception",
        "Traceback",
        "assert",
        "FAILED",
        "[FAIL]",
        "[ERROR]",
        ".py",
        "test_",
        "Expected",
        "Actual",
        "E   ",
    )

    removed = []

    for line in raw.splitlines():
        s = line.strip()

        if not s:
            continue

        if s in rtk_lines:
            continue

        if any(k in s for k in keywords):
            if s not in removed:
                removed.append(s)

    return removed[:limit]


def determine_category(
    removed_exc,
    raw_frames,
    rtk_frames,
    removed_refs,
    removed_assertions,
    removed_tests
):
    categories = []

    if removed_exc:
        categories.append("EXCEPTION_MESSAGE_REMOVED")

    if len(raw_frames) > len(rtk_frames):
        categories.append("STACK_TRACE_REMOVED")

    if removed_refs:
        categories.append("FILE_LINE_CONTEXT_REMOVED")

    if removed_assertions:
        categories.append("ASSERTION_DETAIL_REMOVED")

    if removed_tests:
        categories.append("TEST_IDENTITY_REMOVED")

    if len(categories) == 0:
        return "OTHER_INFORMATION_LOSS"

    if len(categories) >= 3:
        return "MULTIPLE_DEBUGGING_CLUES_REMOVED"

    return "+".join(categories)


print("=" * 75)
print("COMPRESSION TAX ERROR TAXONOMY")
print("=" * 75)

with INPUT_CSV.open() as f:
    rows = list(csv.DictReader(f))

tax_rows = [
    r for r in rows
    if r.get("outcome") == "COMPRESSION_TAX"
]

print(f"Compression Tax cases found: {len(tax_rows)}")
print()

results = []

for i, row in enumerate(tax_rows, 1):

    bug = row["bug"]

    print("#" * 75)
    print(f"[{i}/{len(tax_rows)}] {bug}")
    print("#" * 75)

    raw_path = ROOT / "results" / bug / "raw" / "pytest_output.txt"
    rtk_path = ROOT / "results" / bug / "rtk_static" / "pytest_output.txt"

    raw_eval_path = ROOT / "results" / bug / "raw" / "evaluation_lr.json"
    rtk_eval_path = ROOT / "results" / bug / "rtk_static" / "evaluation_lr.json"

    raw = read_text(raw_path)
    rtk = read_text(rtk_path)

    raw_eval = load_json(raw_eval_path)
    rtk_eval = load_json(rtk_eval_path)

    raw_exc = exception_types(raw)
    rtk_exc = exception_types(rtk)

    removed_exc = sorted(set(raw_exc) - set(rtk_exc))

    raw_frames = traceback_frames(raw)
    rtk_frames = traceback_frames(rtk)

    raw_refs = python_refs(raw)
    rtk_refs = python_refs(rtk)

    removed_refs = sorted(set(raw_refs) - set(rtk_refs))

    raw_tests = test_names(raw)
    rtk_tests = test_names(rtk)

    removed_tests = sorted(set(raw_tests) - set(rtk_tests))

    raw_assert = assertion_lines(raw)
    rtk_assert = assertion_lines(rtk)

    removed_assert = [
        x for x in raw_assert
        if x not in rtk_assert
    ]

    raw_failure = failure_lines(raw)
    rtk_failure = failure_lines(rtk)

    relevant_removed = useful_removed_lines(raw, rtk)

    raw_bytes = len(raw.encode("utf-8"))
    rtk_bytes = len(rtk.encode("utf-8"))

    reduction = (
        100 * (1 - rtk_bytes / raw_bytes)
        if raw_bytes else 0
    )

    category = determine_category(
        removed_exc,
        raw_frames,
        rtk_frames,
        removed_refs,
        removed_assert,
        removed_tests
    )

    raw_top5 = raw_eval.get("top5", [])
    rtk_top5 = rtk_eval.get("top5", [])

    raw_rank = raw_eval.get("file_rank")
    rtk_rank = rtk_eval.get("file_rank")

    overlap = len(set(raw_top5) & set(rtk_top5))

    print(f"RAW bytes              : {raw_bytes}")
    print(f"RTK bytes              : {rtk_bytes}")
    print(f"Reduction              : {reduction:.2f}%")
    print(f"RAW file rank          : {raw_rank}")
    print(f"RTK file rank          : {rtk_rank}")
    print(f"Top-5 overlap          : {overlap}/5")
    print()

    print("RAW exception types    :", raw_exc or "NONE")
    print("RTK exception types    :", rtk_exc or "NONE")
    print("Removed exceptions     :", removed_exc or "NONE")

    print(f"RAW traceback frames   : {len(raw_frames)}")
    print(f"RTK traceback frames   : {len(rtk_frames)}")

    print(f"Removed source refs    : {len(removed_refs)}")
    print(f"Removed assertion info : {len(removed_assert)}")
    print(f"Removed test names     : {len(removed_tests)}")

    print()
    print("Candidate category     :", category)

    print()
    print("Important RAW information missing from RTK:")

    if relevant_removed:
        for line in relevant_removed[:12]:
            print("  -", line)
    else:
        print("  NONE AUTOMATICALLY DETECTED")

    print()

    diff_file = DETAILS / f"{bug}_raw_vs_rtk.diff"

    diff = difflib.unified_diff(
        raw.splitlines(),
        rtk.splitlines(),
        fromfile="RAW",
        tofile="RTK",
        lineterm=""
    )

    diff_file.write_text(
        "\n".join(diff) + "\n",
        encoding="utf-8"
    )

    detail_file = DETAILS / f"{bug}_removed_clues.txt"

    with detail_file.open("w", encoding="utf-8") as f:

        f.write(f"BUG: {bug}\n")
        f.write(f"CATEGORY: {category}\n")
        f.write(f"RAW bytes: {raw_bytes}\n")
        f.write(f"RTK bytes: {rtk_bytes}\n")
        f.write(f"Reduction: {reduction:.2f}%\n")
        f.write(f"RAW rank: {raw_rank}\n")
        f.write(f"RTK rank: {rtk_rank}\n")
        f.write(f"Top5 overlap: {overlap}/5\n\n")

        f.write("REMOVED EXCEPTION TYPES\n")
        for x in removed_exc:
            f.write(f"{x}\n")

        f.write("\nREMOVED TEST NAMES\n")
        for x in removed_tests:
            f.write(f"{x}\n")

        f.write("\nREMOVED SOURCE REFERENCES\n")
        for x in removed_refs:
            f.write(f"{x}\n")

        f.write("\nREMOVED ASSERTION INFORMATION\n")
        for x in removed_assert[:30]:
            f.write(f"{x}\n")

        f.write("\nIMPORTANT REMOVED RAW LINES\n")
        for x in relevant_removed:
            f.write(f"{x}\n")

        f.write("\nRAW TOP 5\n")
        for x in raw_top5:
            f.write(f"{x}\n")

        f.write("\nRTK TOP 5\n")
        for x in rtk_top5:
            f.write(f"{x}\n")

    results.append({
        "bug": bug,
        "raw_rank": raw_rank,
        "rtk_rank": rtk_rank,
        "raw_bytes": raw_bytes,
        "rtk_bytes": rtk_bytes,
        "reduction_percent": f"{reduction:.2f}",
        "raw_traceback_frames": len(raw_frames),
        "rtk_traceback_frames": len(rtk_frames),
        "removed_exception_types": ";".join(removed_exc),
        "removed_source_refs": len(removed_refs),
        "removed_assertion_lines": len(removed_assert),
        "removed_test_names": len(removed_tests),
        "top5_overlap": overlap,
        "category": category,
    })


print()
print("=" * 75)
print("TAXONOMY SUMMARY")
print("=" * 75)

counts = Counter(r["category"] for r in results)

for category, count in counts.most_common():
    print(f"{category:40s} : {count}")

with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(
        f,
        fieldnames=results[0].keys()
    )
    w.writeheader()
    w.writerows(results)


with OUT_MD.open("w", encoding="utf-8") as f:

    f.write("# Compression Tax Error Taxonomy\n\n")

    f.write(
        "This report analyzes SWE-bench SymPy bugs for which "
        "FlexFL successfully localized the gold file using RAW terminal "
        "output but failed when the same debugging evidence was compressed "
        "with RTK.\n\n"
    )

    f.write(f"## Compression Tax Cases\n\n")
    f.write(f"Total cases: **{len(results)}**\n\n")

    f.write("## Taxonomy Summary\n\n")
    f.write("| Category | Cases |\n")
    f.write("|---|---:|\n")

    for category, count in counts.most_common():
        f.write(f"| {category} | {count} |\n")

    f.write("\n## Per-Bug Analysis\n\n")

    for r in results:

        f.write(f"### {r['bug']}\n\n")

        f.write(
            f"- RAW file rank: {r['raw_rank']}\n"
            f"- RTK file rank: {r['rtk_rank']}\n"
            f"- RAW bytes: {r['raw_bytes']}\n"
            f"- RTK bytes: {r['rtk_bytes']}\n"
            f"- Reduction: {r['reduction_percent']}%\n"
            f"- RAW traceback frames: {r['raw_traceback_frames']}\n"
            f"- RTK traceback frames: {r['rtk_traceback_frames']}\n"
            f"- Removed source references: {r['removed_source_refs']}\n"
            f"- Removed assertion lines: {r['removed_assertion_lines']}\n"
            f"- Removed test names: {r['removed_test_names']}\n"
            f"- RAW/RTK Top-5 overlap: {r['top5_overlap']}/5\n"
            f"- Candidate taxonomy: **{r['category']}**\n\n"
        )


print()
print("=" * 75)
print("ANALYSIS COMPLETE")
print("=" * 75)

print("CSV report:")
print(OUT_CSV)

print()
print("Markdown report:")
print(OUT_MD)

print()
print("Detailed per-bug evidence:")
print(DETAILS)
