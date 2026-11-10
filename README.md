# ctxlint

**Lint the instruction files your AI coding agents read on every turn.**

`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, `GEMINI.md` and `.cursor/rules/*` quietly rot. A folder gets renamed, a `typecheck` script gets removed, someone pastes their own `/Users/...` path, and the agent keeps following instructions that are no longer true. `ctxlint` checks those files against the actual repository, the same way a linter checks code.

[![CI](https://github.com/celaldrg/ctxlint/actions/workflows/ci.yml/badge.svg)](https://github.com/celaldrg/ctxlint/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)

- Zero dependencies, pure Python standard library
- Finds every common agent context file, including nested `AGENTS.md` in monorepos
- CI-friendly exit codes and `--json` output

## Install

```bash
pip install git+https://github.com/celaldrg/ctxlint@v0.1.0
# or grab the wheel from the v0.1.0 release
```

## Usage

```bash
ctxlint                 # lint the current repository
ctxlint path/to/repo --budget 2000
ctxlint --json > ctxlint.json
ctxlint -f AGENTS.md --fail-on warning
ctxlint --list-rules
```

## Example

Running it on [`examples/demo`](examples/demo):

```text
$ ctxlint examples/demo
  AGENTS.md                                    ~    80 tokens
  CLAUDE.md                                    ~    48 tokens
  total                                        ~   128 tokens

AGENTS.md:3: error CL001 referenced path `src/handlers/` does not exist
AGENTS.md:4: error CL004 script `typecheck` is not defined in package.json
AGENTS.md:5: error CL002 link target `docs/architecture.md` does not exist
AGENTS.md:5: error CL005 make target `deploy` is not defined in Makefile
AGENTS.md:7: info CL008 paragraph duplicated in CLAUDE.md:3; keep one source of truth (e.g. AGENTS.md) and reference it
CLAUDE.md:5: warning CL007 machine-specific path `/Users/alex` will not exist for teammates or CI agents

2 file(s), 4 error(s), 1 warning(s), 1 info
```

## Rules

| Rule  | Severity | What it catches |
|-------|----------|-----------------|
| CL000 | warning | Empty context file |
| CL001 | error   | A path in `backticks` that does not exist (resolved from the file's folder and the repo root) |
| CL002 | error   | A Markdown link to a local file that does not exist |
| CL003 | warning | File is larger than the token budget (default 4000, about 4 chars per token) |
| CL004 | error   | `npm run` / `pnpm run` / `bun run` / `yarn` script missing from `package.json` |
| CL005 | error   | `make` target missing from the `Makefile` |
| CL006 | error   | Secret-looking strings: AWS keys, GitHub and Slack tokens, `sk-` API keys, private key blocks |
| CL007 | warning | Machine-specific home paths such as `/Users/alex` or `C:\Users\alex` |
| CL008 | info    | The same paragraph copied into several context files, which drift apart over time |

Text inside fenced code blocks and obvious placeholders (`src/<name>.ts`, `your/file.py`, `*.go`) are not treated as paths. Skip a rule with `--ignore CL008`.

## Files it looks for

`AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md`, plus everything in `.cursor/rules/`, `.github/instructions/` and `.clinerules/`, and nested `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` up to four folders deep (skipping `node_modules`, `vendor`, build output and hidden folders).

## GitHub Actions

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install git+https://github.com/celaldrg/ctxlint@v0.1.0
- run: ctxlint --budget 3000
```

## Exit codes

`0` clean (or below `--fail-on`), `1` findings at or above `--fail-on` (default `error`), `2` bad arguments.

## Related

Inspired by the [AGENTS.md](https://agents.md) convention. Pairs well with [skillcheck](https://github.com/celaldrg/skillcheck) for Agent Skills and [tokmap](https://github.com/celaldrg/tokmap) for whole-repo token costs.

## License

MIT © Celalettin Durğaç
