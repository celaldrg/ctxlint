"""Discovery and checks for agent context files. Standard library only."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path

# Well-known instruction files read by coding agents.
CONTEXT_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "GEMINI.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    ".github/copilot-instructions.md",
]
CONTEXT_DIRS = [".cursor/rules", ".github/instructions", ".clinerules"]
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "target", "__pycache__"}

SEVERITY_ORDER = {"error": 2, "warning": 1, "info": 0}


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    severity: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def discover(root: Path, max_depth: int = 4) -> list[Path]:
    """Return context files under root (nested AGENTS.md/CLAUDE.md included)."""
    found: set[Path] = set()
    for rel in CONTEXT_FILES:
        p = root / rel
        if p.is_file():
            found.add(p)
    for rel in CONTEXT_DIRS:
        d = root / rel
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and p.suffix in {".md", ".mdc", ".txt", ""}:
                    found.add(p)
    names = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if depth >= max_depth:
            dirnames[:] = []
        for f in filenames:
            if f in names:
                found.add(Path(dirpath) / f)
    return sorted(found)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code mixes."""
    return (len(text) + 3) // 4


# --- project facts -----------------------------------------------------------

def load_npm_scripts(root: Path) -> set[str] | None:
    pkg = root / "package.json"
    if not pkg.is_file():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return set((data.get("scripts") or {}).keys())


_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_.\-/]+)\s*:(?!=)")


def load_make_targets(root: Path) -> set[str] | None:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        mk = root / name
        if mk.is_file():
            targets = set()
            for line in mk.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _MAKE_TARGET.match(line)
                if m:
                    for t in line.split(":", 1)[0].split():
                        targets.add(t)
            return targets
    return None


# --- checks -------------------------------------------------------------------

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_PATHLIKE = re.compile(r"^(\./|\.\./)?[A-Za-z0-9_\-.]+(/[A-Za-z0-9_\-.]+)*/?$")
_KNOWN_EXT = {
    "md", "mdc", "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "go", "rs", "java", "kt", "rb",
    "php", "cs", "c", "h", "cpp", "hpp", "swift", "json", "yaml", "yml", "toml", "ini", "sh",
    "sql", "css", "scss", "html", "vue", "svelte", "lock", "txt", "env", "cfg",
}
_NPM_RUN = re.compile(r"\b(?:npm|pnpm|bun)\s+run\s+([A-Za-z0-9:_\-.]+)|\byarn\s+(?:run\s+)?([A-Za-z0-9:_\-.]+)")
_YARN_BUILTINS = {"install", "add", "remove", "upgrade", "init", "why", "dlx", "workspace", "workspaces", "set", "config", "info", "global", "cache", "link", "unlink", "run", "exec", "node", "up", "create", "audit", "outdated", "pack", "publish", "version", "--version", "-v"}
_MAKE_CALL = re.compile(r"(?:^|[\s`$])make\s+([A-Za-z0-9_.\-/]+)")
_SECRETS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{32,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]
_HOME_PATH = re.compile(r"(/Users/[A-Za-z0-9._\-]+|/home/[A-Za-z0-9._\-]+|[A-Z]:\\Users\\[A-Za-z0-9._\-]+)")
_PLACEHOLDER = re.compile(r"[<>{}*$]|\b(?:your|example|foo|bar)\b", re.I)


def _looks_like_path(token: str) -> bool:
    token = token.strip()
    if not token or " " in token or "://" in token or token.startswith(("-", "@", "#")):
        return False
    if _PLACEHOLDER.search(token) or not _PATHLIKE.match(token):
        return False
    last = token.rstrip("/").rsplit("/", 1)[-1]
    if "/" in token:
        return True
    # bare file name: require a known extension and no version-like dots
    if "." in last:
        ext = last.rsplit(".", 1)[-1].lower()
        return ext in _KNOWN_EXT and not re.match(r"^\d", last)
    return False


def _iter_lines(text: str):
    """Yield (lineno, line, in_code_block)."""
    fence = None
    for i, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            mark = s[:3]
            fence = None if fence == mark else (fence or mark)
            yield i, line, True
            continue
        yield i, line, fence is not None


def check_file(path: Path, root: Path, budget: int, scripts, targets) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[Finding] = []

    if not text.strip():
        out.append(Finding(rel, 1, "CL000", "warning", "context file is empty"))
        return out

    tokens = estimate_tokens(text)
    if budget and tokens > budget:
        out.append(Finding(rel, 1, "CL003", "warning",
                           f"~{tokens} tokens exceeds budget of {budget}; agents load this on every turn"))

    seen_paths: set[str] = set()
    for lineno, line, in_code in _iter_lines(text):
        # CL001 / CL002: referenced paths and links that do not exist
        if not in_code:
            for m in _CODE_SPAN.finditer(line):
                cand = m.group(1).strip()
                if _looks_like_path(cand) and cand not in seen_paths:
                    seen_paths.add(cand)
                    if not _exists(cand, path, root):
                        out.append(Finding(rel, lineno, "CL001", "error",
                                           f"referenced path `{cand}` does not exist"))
            for m in _MD_LINK.finditer(line):
                target = m.group(1).split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                if not _exists(target, path, root):
                    out.append(Finding(rel, lineno, "CL002", "error",
                                       f"link target `{target}` does not exist"))

        # CL004: npm/yarn/pnpm scripts that are not defined
        if scripts is not None:
            for m in _NPM_RUN.finditer(line):
                name = m.group(1) or m.group(2)
                if m.group(2) and name in _YARN_BUILTINS:
                    continue
                if name and name not in scripts:
                    out.append(Finding(rel, lineno, "CL004", "error",
                                       f"script `{name}` is not defined in package.json"))
        # CL005: make targets that are not defined
        if targets is not None:
            for m in _MAKE_CALL.finditer(line):
                t = m.group(1)
                if t.startswith("-") or t in targets:
                    continue
                out.append(Finding(rel, lineno, "CL005", "error",
                                   f"make target `{t}` is not defined in Makefile"))

        # CL006: secrets
        for label, rx in _SECRETS:
            if rx.search(line):
                out.append(Finding(rel, lineno, "CL006", "error",
                                   f"possible {label} committed in an agent context file"))
        # CL007: machine-specific home paths
        hm = _HOME_PATH.search(line)
        if hm and not _PLACEHOLDER.search(hm.group(0)):
            out.append(Finding(rel, lineno, "CL007", "warning",
                               f"machine-specific path `{hm.group(0)}` will not exist for teammates or CI agents"))
    return out


def _exists(ref: str, ctx_file: Path, root: Path) -> bool:
    ref = ref.strip()
    clean = ref.lstrip("/") if ref.startswith("/") else ref
    candidates = [ctx_file.parent / ref, root / clean]
    return any(c.exists() for c in candidates)


def _normalize_block(block: str) -> str:
    return re.sub(r"\s+", " ", block.strip().lower())


def check_duplicates(files: list[Path], root: Path, min_chars: int = 60) -> list[Finding]:
    """CL008: identical paragraphs copied across several context files drift apart."""
    index: dict[str, list[tuple[str, int]]] = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(root).as_posix()
        lineno, start, buf = 0, 1, []
        for lineno, line in enumerate(text.splitlines() + [""], 1):
            if line.strip():
                if not buf:
                    start = lineno
                buf.append(line)
            elif buf:
                key = _normalize_block("\n".join(buf))
                if len(key) >= min_chars:
                    index.setdefault(key, [])
                    if not any(r == rel for r, _ in index[key]):
                        index[key].append((rel, start))
                buf = []
    out = []
    for key, locs in index.items():
        if len(locs) > 1:
            others = ", ".join(f"{r}:{l}" for r, l in locs[1:])
            r0, l0 = locs[0]
            out.append(Finding(r0, l0, "CL008", "info",
                               f"paragraph duplicated in {others}; keep one source of truth (e.g. AGENTS.md) and reference it"))
    return out


def lint(root: Path, files: list[Path] | None = None, budget: int = 4000) -> tuple[list[Path], list[Finding]]:
    root = root.resolve()
    files = [f.resolve() for f in files] if files else discover(root)
    scripts = load_npm_scripts(root)
    targets = load_make_targets(root)
    findings: list[Finding] = []
    for f in files:
        findings.extend(check_file(f, root, budget, scripts, targets))
    findings.extend(check_duplicates(files, root))
    findings.sort(key=lambda x: (x.file, x.line, x.rule))
    return files, findings
