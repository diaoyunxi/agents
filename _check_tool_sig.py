import sys, importlib.util, inspect
from pathlib import Path

sys.path.insert(0, ".")
import config

root = Path(config.tools_dir())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


rows = []
for folder in sorted(root.iterdir()):
    if not folder.is_dir() or folder.name.startswith((".", "_")):
        continue
    impl = folder / "tools.py"
    if not impl.exists():
        continue
    try:
        m = load(impl, "check_" + folder.name)
    except Exception:
        continue
    run = getattr(m, "run", None)
    if not callable(run):
        continue
    sig = inspect.signature(run)
    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    sig_params = set(sig.parameters)
    required_sig = [n for n, p in sig.parameters.items()
                    if p.default is inspect.Parameter.empty
                    and p.kind != inspect.Parameter.VAR_KEYWORD]
    schema = getattr(m, "PARAMETERS", {}) or {}
    props = schema.get("properties", {}) or {}
    schema_required = set(schema.get("required", []) or [])
    schema_props = set(props)

    missing_in_sig = [r for r in schema_required if r not in sig_params]
    sig_req_not_in_schema = [r for r in required_sig if r not in schema_props]

    problems = []
    if has_varkw:
        varkw_note = "varkw"
        # 有 **kwargs 时不会 TypeError，但 schema required 仍应准确
    else:
        varkw_note = "no-varkw"
        if missing_in_sig:
            problems.append("missing_in_sig=" + ",".join(missing_in_sig))
        if sig_req_not_in_schema:
            problems.append("sig_req_not_in_schema=" + ",".join(sig_req_not_in_schema))

    line = "%-26s %-9s sig=%s" % (folder.name, varkw_note, sorted(sig_params))
    if problems:
        line += "  <<< " + " | ".join(problems)
    print(line)
