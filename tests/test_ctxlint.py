import json
import tempfile
import unittest
from pathlib import Path

from ctxlint.cli import main
from ctxlint.core import discover, estimate_tokens, lint


def make(tmp: Path, files: dict):
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class CtxlintTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def rules(self, findings):
        return sorted(f.rule for f in findings)

    def test_discover_known_files(self):
        make(self.root, {
            "AGENTS.md": "x", "CLAUDE.md": "x", ".cursorrules": "x",
            ".github/copilot-instructions.md": "x", ".cursor/rules/style.mdc": "x",
            "packages/api/AGENTS.md": "x", "node_modules/pkg/AGENTS.md": "x", "README.md": "x",
        })
        got = [p.relative_to(self.root).as_posix() for p in discover(self.root)]
        self.assertIn("packages/api/AGENTS.md", got)
        self.assertIn(".cursor/rules/style.mdc", got)
        self.assertNotIn("node_modules/pkg/AGENTS.md", got)
        self.assertNotIn("README.md", got)
        self.assertEqual(len(got), 6)

    def test_clean_project_has_no_findings(self):
        make(self.root, {
            "src/app.py": "", "package.json": json.dumps({"scripts": {"test": "x", "lint": "y"}}),
            "Makefile": "build:\n\techo hi\n",
            "AGENTS.md": "Code lives in `src/app.py`. Run `npm run test` and `make build`.\n"
                         "See [the app](src/app.py). Version `1.2.3` and flag `--fix` are fine.\n",
        })
        _, findings = lint(self.root)
        self.assertEqual(findings, [])

    def test_missing_path_and_link(self):
        make(self.root, {"AGENTS.md": "Edit `src/old_module.py` and read [docs](docs/setup.md).\n"})
        _, findings = lint(self.root)
        self.assertEqual(self.rules(findings), ["CL001", "CL002"])

    def test_relative_to_nested_file(self):
        make(self.root, {"pkg/AGENTS.md": "Entry point is `main.go`.\n", "pkg/main.go": ""})
        _, findings = lint(self.root)
        self.assertEqual(findings, [])

    def test_paths_in_code_blocks_are_ignored(self):
        make(self.root, {"AGENTS.md": "```\ncat `nope/file.py`\n```\n"})
        _, findings = lint(self.root)
        self.assertEqual(findings, [])

    def test_placeholders_are_not_paths(self):
        make(self.root, {"AGENTS.md": "Create `src/<name>.ts` or `your/file.py` or `*.go`.\n"})
        _, findings = lint(self.root)
        self.assertEqual(findings, [])

    def test_missing_npm_script_and_make_target(self):
        make(self.root, {
            "package.json": json.dumps({"scripts": {"test": "x"}}),
            "Makefile": "test:\n\tgo test\n",
            "CLAUDE.md": "Run `pnpm run typecheck`, `yarn lint`, `yarn install` and `make deploy`.\n",
        })
        _, findings = lint(self.root)
        msgs = [f.message for f in findings]
        self.assertEqual(self.rules(findings), ["CL004", "CL004", "CL005"])
        self.assertTrue(any("typecheck" in m for m in msgs))
        self.assertFalse(any("install" in m for m in msgs))

    def test_no_package_json_means_no_script_checks(self):
        make(self.root, {"AGENTS.md": "Run `npm run whatever`.\n"})
        _, findings = lint(self.root)
        self.assertEqual(findings, [])

    def test_secrets(self):
        make(self.root, {"AGENTS.md": "token ghp_" + "a" * 36 + "\nkey AKIA" + "B" * 16 + "\n"})
        _, findings = lint(self.root)
        self.assertEqual(self.rules(findings), ["CL006", "CL006"])

    def test_home_paths(self):
        make(self.root, {".cursorrules": "Python is at /Users/celal/.pyenv/bin/python\n"})
        _, findings = lint(self.root)
        self.assertEqual(self.rules(findings), ["CL007"])

    def test_budget(self):
        make(self.root, {"AGENTS.md": "word " * 1000})
        _, findings = lint(self.root, budget=500)
        self.assertEqual(self.rules(findings), ["CL003"])
        _, findings = lint(self.root, budget=0)
        self.assertEqual(findings, [])

    def test_duplicates_across_files(self):
        para = "Always write tests for new behaviour and run the full suite before committing anything.\n"
        make(self.root, {"AGENTS.md": "# A\n\n" + para, "CLAUDE.md": "# C\n\n" + para})
        _, findings = lint(self.root)
        self.assertEqual(self.rules(findings), ["CL008"])
        self.assertEqual(findings[0].severity, "info")

    def test_empty_file(self):
        make(self.root, {"GEMINI.md": "  \n"})
        _, findings = lint(self.root)
        self.assertEqual(self.rules(findings), ["CL000"])

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)

    def test_cli_exit_codes_and_json(self):
        make(self.root, {"AGENTS.md": "See `missing.py`. Lives at /home/bob/x\n"})
        self.assertEqual(main([str(self.root), "--json"]), 1)
        self.assertEqual(main([str(self.root), "--ignore", "CL001"]), 0)
        self.assertEqual(main([str(self.root), "--ignore", "CL001", "--fail-on", "warning"]), 1)
        self.assertEqual(main([str(self.root), "--fail-on", "never"]), 0)

    def test_cli_no_files(self):
        self.assertEqual(main([str(self.root)]), 0)


if __name__ == "__main__":
    unittest.main()
