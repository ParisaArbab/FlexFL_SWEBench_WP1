"""FlexFL Agent4SR / Agent4LR adapted to SWE-bench.

The control flow follows the original FlexFL `pipeline.py`:
- same SR vs LR stages
- same 10 tool-call budget
- same iterative function-call protocol
- same final Top_1 ... Top_5 answer format

Dataset/language changes are limited to SWE-bench input fields and Python corpus tools.
The default model remains Llama-3-8B-Instruct to match the replication package.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from function_call_swebench import (
    find_class,
    find_method,
    get_classes,
    get_code_snippet,
    get_methods,
    get_paths,
)

# Construction of open-source model, intentionally kept equivalent to FlexFL.
model_name = "Llama3"


def build_llama():
    from llama import Llama

    ckpt_dir: str = os.environ.get("LLAMA3_CKPT_DIR", "Meta-Llama-3-8B-Instruct/")
    tokenizer_path: str = os.environ.get("LLAMA3_TOKENIZER", "Meta-Llama-3-8B-Instruct/tokenizer.model")
    return Llama.build(
        ckpt_dir=ckpt_dir,
        tokenizer_path=tokenizer_path,
        max_seq_len=8192,
        max_batch_size=1,
        seed=42,
    )


def query(generator, instruction):
    results = generator.chat_completion(
        [instruction],
        max_gen_len=None,
        temperature=0,
        top_p=1.0,
    )
    result = results[0]
    print(f"> {result['generation']['role'].capitalize()}: {result['generation']['content']}")
    return result["generation"]["content"].strip()


def tool_description(stage: str) -> str:
    if stage == "SR":
        return """
Function calls you can use are as follows.
* find_class(`class_name`) -> Find a Python class in the software system by fuzzy search. *
* find_method(`method_name`) -> Find a function/method by fuzzy search. *
* get_paths() -> Get the Python module paths of the software system. *
* get_classes_of_path(`path_name`) -> Get classes in a Python module path. *
* get_methods_of_class(`class_name`) -> Get methods belonging to a class/module. *
* get_code_snippet_of_method(`method_name`) -> Get the code snippet of the Python function/method. *
* exit() -> Exit function calling to give your final answer when you are confident of the answer. *
"""
    return """
Function calls you can use are as follows.
* get_code_snippet_of_method(`method_number`) -> Get the code snippet of the numbered suggested method. *
* exit() -> Exit function calling to give your final answer when you are confident of the answer. *
"""


def load_bug_list(data_root: Path) -> list[str]:
    with (data_root / "bug_list" / "SWEbench" / "bug_list.txt").open() as f:
        return [e.strip() for e in f if e.strip()]


def run_bug(generator, bug: str, stage: str, rank: str, data_root: Path, res_root: Path):
    dataset = "SWEbench"
    max_try = 10
    input_type = "All"

    input_description = ""
    bug_report_path = data_root / "input" / "bug_reports" / dataset / f"{bug}.json"
    trigger_path = data_root / "input" / "trigger_tests" / dataset / f"{bug}.txt"

    input_type_a = None
    if bug_report_path.exists():
        bug_report = json.loads(bug_report_path.read_text(encoding="utf-8"))
        input_type_a = "a bug report"
        input_description += (
            "The bug report is as follows:\n```\n"
            f"Title:{bug_report['title']}\nDescription:{bug_report['description']}\n```\n"
        )
    if trigger_path.exists():
        input_type_a = f"{input_type_a}, a trigger test" if input_type_a else "a trigger test"
        input_description += f"The trigger test is as follows:\n```\n{trigger_path.read_text(encoding='utf-8')}\n```\n"
    if input_type_a is None:
        raise RuntimeError(f"No bug report or trigger test found for {bug}")

    suspicious_methods = None
    if stage == "LR":
        suspicious_path = data_root / "input" / "suspicious_methods" / dataset / f"{model_name}_{rank}" / f"{bug}.txt"
        suspicious_methods = [e for e in suspicious_path.read_text(encoding="utf-8").splitlines() if e.strip()]
        content = "\n".join(f"{i}.{m}" for i, m in enumerate(suspicious_methods, 1))
        input_description += f"The suggested methods are as follows:\n```\n{content}\n```\n"

    functions = tool_description(stage)
    input_type_the = input_type_a.replace("a ", "the ")
    instruction = [
        {
            "role": "system",
            "content": (
                f"You are a debugging assistant of our Python software. You will be presented with {input_type_a} "
                "and tools (functions) to access the source code of the system under test (SUT). "
                f"Your task is to locate the top-5 most likely culprit methods based on {input_type_the} and the "
                f"information you retrieve using given functions. {functions}\nYou have {max_try} chances to call function."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{input_description}Let's locate the faulty method step by step using reasoning and function calls. "
                "Now reason and plan how to locate the buggy methods."
            ),
        },
    ]

    content = query(generator, instruction)
    instruction.append({"role": "Assistant", "content": content})

    for _ in range(max_try):
        instruction.append({
            "role": "user",
            "content": "Now call a function in this format `FunctionName(Argument)` in a single line without any other word.",
        })
        content = query(generator, instruction)
        instruction.append({"role": "Assistant", "content": content})
        try:
            call = content.replace("'", "").replace('"', "")
            name = call[: call.find("(")].strip()
            arg = call[call.find("(") + 1 : call.rfind(")")].strip().strip("`")
            if name == "get_paths":
                retval = get_paths(bug, dataset)
            elif name == "get_classes_of_path":
                retval = get_classes(bug, arg, dataset)
            elif name == "get_methods_of_class":
                retval = get_methods(bug, arg, dataset)
            elif name == "get_code_snippet_of_method":
                if stage == "SR":
                    retval = get_code_snippet(bug, arg, dataset)
                else:
                    idx = int(arg) - 1
                    retval = get_code_snippet(bug, suspicious_methods[idx], dataset)
                    retval = f"The code snippet of {suspicious_methods[idx]} is as follows.\n" + retval
            elif name == "find_class":
                retval = find_class(bug, arg, dataset)
            elif name == "find_method":
                retval = find_method(bug, arg, dataset)
            elif name == "exit":
                break
            else:
                instruction.append({"role": "user", "content": "Please call functions in the right format `FunctionName(Argument)`." + functions})
                continue
            print(retval)
            instruction.append({"role": "user", "content": retval})
        except Exception as exc:
            print(exc)
            instruction.append({"role": "user", "content": "Please call functions in the right format `FunctionName(Argument)`." + functions})

    instruction.append({
        "role": "user",
        "content": (
            "Based on the available information, provide complete name of the top-5 most likely culprit methods for the bug please. "
            "Since your answer will be processed automatically, please give your answer in the format as follows.\n"
            "Top_1 : PathName.ClassName.MethodName()\n"
            "Top_2 : PathName.ClassName.MethodName()\n"
            "Top_3 : PathName.ClassName.MethodName()\n"
            "Top_4 : PathName.ClassName.MethodName()\n"
            "Top_5 : PathName.ClassName.MethodName()\n"
        ),
    })
    content = query(generator, instruction)
    instruction.append({"role": "Assistant", "content": content})

    output_dir = res_root / (f"{model_name}_{dataset}_SR" if stage == "SR" else f"{model_name}_{dataset}_{rank}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{bug}.json").write_text(json.dumps(instruction, indent=4), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="SWEbench", choices=["SWEbench"])
    parser.add_argument("--input", default="All", choices=["bug_report", "trigger_test", "All"])
    parser.add_argument("--stage", default="SR", choices=["SR", "LR"])
    parser.add_argument("--rank", default="All")
    parser.add_argument("--bug", default=None)
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    data_root = here.parent / "data"
    res_root = here.parent / "res"
    bugs = [args.bug] if args.bug else load_bug_list(data_root)
    generator = build_llama()
    for bug in bugs:
        print(bug)
        run_bug(generator, bug, args.stage, args.rank, data_root, res_root)


if __name__ == "__main__":
    main()
