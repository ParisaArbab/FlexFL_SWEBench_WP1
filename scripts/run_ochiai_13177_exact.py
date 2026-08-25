from pathlib import Path
import generate_ochiai_sympy as g

BUG = "sympy__sympy-13177"

# Keep original functions
original_resolve = g.resolve_fail_tests
original_coverage = g.run_sympy_coverage


# For this SWE-bench instance, test_mod reproduces the failure.
# test_mod_inverse is listed in FAIL_TO_PASS metadata but does not
# reproduce as failing in our validated environment.
def resolve_fail_tests_13177(bug, repo, index):
    result = original_resolve(bug, repo, index)

    if bug == BUG:
        print()
        print("===== 13177 REPRODUCING FAIL_TO_PASS =====")

        filtered = [
            item for item in result
            if item[1] == "test_mod"
        ]

        for item in result:
            if item[1] != "test_mod":
                print(
                    "SKIP NON-REPRODUCING FAIL_TO_PASS:",
                    item[0],
                    item[1],
                )

        print("Using:", filtered)

        if not filtered:
            raise RuntimeError("Could not resolve exact test_mod")

        return filtered

    return result


# SymPy -k performs substring matching.
# Therefore "-k test_mod" also executes test_mod_inverse.
# For this one failing test, execute the exact function directly.
def run_coverage_13177(
    repo,
    test_file,
    test_name,
    output,
    should_fail,
):
    if (
        repo.name != BUG
        or test_name != "test_mod"
        or not should_fail
    ):
        return original_coverage(
            repo,
            test_file,
            test_name,
            output,
            should_fail,
        )

    env = g.repo_env(repo)

    print()
    print("===== EXACT COVERAGE: test_mod ONLY =====")

    g.run(
        [g.TEST_PYTHON, "-m", "coverage", "erase"],
        repo,
        env,
    )

    module = test_file[:-3].replace("/", ".")

    runner = Path("/tmp/flexfl_13177_exact_test.py")

    runner.write_text(
        f"from {module} import {test_name}\n"
        f"{test_name}()\n",
        encoding="utf-8",
    )

    result = g.run(
        [
            g.TEST_PYTHON,
            "-m",
            "coverage",
            "run",
            "--branch",
            str(runner),
        ],
        repo,
        env,
    )

    print(result.stdout[-3000:])

    print("Exact test exit code:", result.returncode)

    if result.returncode != 1:
        print("ERROR: exact test_mod did not fail")
        return False

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = g.run(
        [
            g.TEST_PYTHON,
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

    print("Exact failing coverage saved:", output)

    return True


g.resolve_fail_tests = resolve_fail_tests_13177
g.run_sympy_coverage = run_coverage_13177

print("=" * 70)
print("RUNNING CORRECTED OCHIAI FOR", BUG)
print("=" * 70)

g.generate(BUG)

print()
print("=" * 70)
print("13177 OCHIAI COMPLETE")
print("=" * 70)
