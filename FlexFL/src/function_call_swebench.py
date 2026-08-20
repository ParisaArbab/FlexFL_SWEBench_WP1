"""SWE-bench/Python adapter for the original FlexFL function-call API.

Function names and return behavior intentionally mirror FlexFL's original
`function_call.py`. Only corpus naming/parsing is adapted for Python.
"""

from pathlib import Path
from difflib import SequenceMatcher

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "input" / "buggy_program"


def _paths(bug, dataset):
    base = DATA_ROOT / dataset
    return (
        base / f"{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity",
        base / f"{bug}.corpusRawMethodLevelGranularity",
    )


def split4search(query):
    if "(" not in query:
        return query.replace("$", ".").split(".")
    signature = query[query.find("(") + 1 : query.find(")")]
    method = query[: query.find("(")]
    return method.replace("$", ".").split(".") + [e.strip().split(".")[-1] for e in signature.split(",") if e.strip()]


def _distance(a, b):
    return int(round((1.0 - SequenceMatcher(None, a, b).ratio()) * max(len(a), len(b))))


def fuzzy_search(query, choices):
    query = query.replace("#", ".").replace("$", ".")
    match_res = []
    querys = split4search(query)
    for choice in choices:
        match_choice = split4search(choice)
        if all(q in match_choice for q in querys):
            match_res.append(choice)
    if not match_res:
        distances = sorted(((choice, _distance(query, choice.replace("$", "."))) for choice in choices), key=lambda x: x[1])
        match_res = [c for c, d in distances if d <= 5]
        if not match_res:
            match_res = [c for c, _ in distances[:5]]
    return match_res


def _load(bug, dataset):
    mapping_file, raw_file = _paths(bug, dataset)
    methods = [e.strip() for e in mapping_file.read_text(encoding="utf-8").splitlines() if e.strip()]
    codes = [e.strip().replace("\\n", "\n") for e in raw_file.read_text(encoding="utf-8").splitlines()]
    return methods, codes


def get_code_snippet(bug, function, dataset):
    function = function.replace(", ", ",").replace(" ,", ",")
    methods, codes = _load(bug, dataset)
    normalized = function.replace("$", ".")
    for method, code in zip(methods, codes):
        if method.replace("$", ".") == normalized:
            return code
    normalized_methods = [m.replace("$", ".") for m in methods]
    results = fuzzy_search(normalized, normalized_methods)
    if len(results) == 1:
        method = results[0]
        code = get_code_snippet(bug, method, dataset)
        return f"Do you mean `{method}`? Its code snippet is as follows.\n{code}"
    if not results:
        return "You provide a wrong method name. You can call `get_methods_of_class` first to get a right method name."
    return "You provide a wrong method name. Please try the following method names.\n" + "\n".join(results)


def get_paths(bug, dataset):
    methods, _ = _load(bug, dataset)
    paths = sorted(set(e.split("$")[0] for e in methods))
    return "\n".join(paths)


def get_classes(bug, path_name, dataset):
    methods, _ = _load(bug, dataset)
    classes = []
    for e in methods:
        if not e.startswith(path_name + "$"):
            continue
        scope = e.split("$", 1)[1].split("(")[0].split(".")
        if len(scope) > 1:
            classes.append(".".join(scope[:-1]))
    classes = sorted(set(classes))
    if classes:
        return "\n".join(classes)
    paths = sorted(set(e.split("$")[0] for e in methods))
    results = fuzzy_search(path_name, paths)
    if len(results) == 1:
        return f"Do you mean `{results[0]}`? Its classes are as follows.\n{get_classes(bug, results[0], dataset)}"
    if results:
        return "You provide a wrong path name. Please try the following path names.\n" + "\n".join(sorted(results))
    return "You provide a wrong path name. You can call `get_paths` first to get a right path name."


def get_methods(bug, class_name, dataset):
    methods, _ = _load(bug, dataset)
    found = []
    for e in methods:
        normalized = e.replace("$", ".")
        pos = normalized.find("(")
        owner = ".".join(normalized[:pos].split(".")[:-1])
        if owner == class_name:
            found.append(normalized[len(owner) + 1 :])
    found = sorted(set(found))
    if found:
        return "\n".join(found)
    classes = []
    for e in methods:
        normalized = e.replace("$", ".")
        pos = normalized.find("(")
        classes.append(".".join(normalized[:pos].split(".")[:-1]))
    results = fuzzy_search(class_name, sorted(set(classes)))
    if len(results) == 1:
        return f"Do you mean `{results[0]}`? Its methods are as follows.\n{get_methods(bug, results[0], dataset)}"
    if results:
        return "You provide a wrong class name. Please try the following class names.\n" + "\n".join(sorted(results))
    return "You provide a wrong class name. You can call `get_classes_of_path` first to get a right class name."


def find_class(bug, class_name, dataset):
    methods, _ = _load(bug, dataset)
    classes = []
    for e in methods:
        normalized = e.replace("$", ".")
        pos = normalized.find("(")
        classes.append(".".join(normalized[:pos].split(".")[:-1]))
    classes = sorted(set(classes))
    if "." in class_name:
        found = fuzzy_search(class_name, classes)
    else:
        found = [c for c in classes if c.split(".")[-1] == class_name]
        if not found:
            short = sorted(set(c.split(".")[-1] for c in classes))
            found = fuzzy_search(class_name, short)
    return "\n".join(sorted(found))


def find_method(bug, method_name, dataset):
    methods, _ = _load(bug, dataset)
    normalized = [e.replace("$", ".") for e in methods]
    return "\n".join(fuzzy_search(method_name, sorted(set(normalized))))
