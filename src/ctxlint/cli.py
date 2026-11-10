from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import SEVERITY_ORDER, estimate_tokens, lint

RULES = {
    "CL000": "empty context file",
    "CL001": "referenced path does not exist",
    "CL002": "markdown link target does not exist",
    "CL003": "file exceeds token budget",
    "CL004": "npm/yarn/pnpm script not defined in package.json",
    "CL005": "make target not defined in Makefile",
    "CL006": "secret-like string in context file",
    "CL007": "machine-specific home directory path",
    "CL008": "paragraph duplicated across context files",
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ctxlint",
        description="Lint AI agent context files (AGENTS.md, CLAUDE.md, .cursorrules, copilot-instructions.md, ...) "
                    "for stale paths, missing scripts, leaked secrets and token bloat.",
    )
    p.add_argument("root", nargs="?", default=".", help="project root (default: .)")
    p.add_argument("-f", "--file", action="append", type=Path, help="lint only this file (repeatable)")
    p.add_argument("--budget", type=int, default=4000, help="per-file token budget, 0 disables (default 4000)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--fail-on", choices=["error", "warning", "info", "never"], default="error",
                   help="lowest severity that causes exit code 1 (default: error)")
    p.add_argument("--ignore", action="append", default=[], help="rule id to skip, e.g. CL008 (repeatable)")
    p.add_argument("--list-rules", action="store_true", help="print rule ids and exit")
    p.add_argument("--version", action="version", version=f"ctxlint {__version__}")
    a = p.parse_args(argv)

    if a.list_rules:
        for k, v in RULES.items():
            print(f"{k}  {v}")
        return 0

    root = Path(a.root)
    if not root.is_dir():
        print(f"ctxlint: {root} is not a directory", file=sys.stderr)
        return 2
    files, findings = lint(root, a.file, a.budget)
    findings = [f for f in findings if f.rule not in set(a.ignore)]
    rroot = root.resolve()

    if a.json:
        print(json.dumps({
            "files": [{"path": f.relative_to(rroot).as_posix(),
                       "tokens": estimate_tokens(f.read_text(encoding="utf-8", errors="replace"))} for f in files],
            "findings": [f.to_dict() for f in findings],
        }, indent=2))
    else:
        if not files:
            print("ctxlint: no agent context files found (AGENTS.md, CLAUDE.md, .cursorrules, ...)")
            return 0
        total = 0
        for f in files:
            t = estimate_tokens(f.read_text(encoding="utf-8", errors="replace"))
            total += t
            print(f"  {f.relative_to(rroot).as_posix():<44} ~{t:>6} tokens")
        print(f"  {'total':<44} ~{total:>6} tokens\n")
        for f in findings:
            print(f"{f.file}:{f.line}: {f.severity} {f.rule} {f.message}")
        counts = {s: sum(1 for f in findings if f.severity == s) for s in ("error", "warning", "info")}
        print(f"\n{len(files)} file(s), {counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info")

    if a.fail_on == "never":
        return 0
    threshold = SEVERITY_ORDER[a.fail_on]
    return 1 if any(SEVERITY_ORDER[f.severity] >= threshold for f in findings) else 0
