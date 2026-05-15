# Unity Build Regression Tool

## What this is
CLI tool that detects Unity build regressions by diffing build logs.
`builddiff_advanced.py` — 240 GitHub clones. Open source, Python CLI.

## Hard rules

These apply to `builddiff_advanced.py`, tests, and CI yaml.

1. **No em-dashes.** Never U+2014. Same ban for en-dash U+2013, curly quotes, ellipsis U+2026. ASCII only — `--help` output and stderr included.
2. **No AI-style annotations.** Do not add `[FIX-N]`, `[NEW-N]`, or any bracketed change tag.
3. **No AI-style phrasings** in comments, docstrings, or `--help` text: drop "Let's", "we'll", "we then", "in order to", "simply", "elegant", "robust", "comprehensive", "seamlessly", "leverages", "Note that", "It's worth noting".
4. **Single-file CLI is intentional** — the `# === SECTION ===` banners that grow inside one large script are tolerated here only because splitting breaks the `curl-and-run` story. Keep banner count low; prefer well-named functions.
5. **Default to no comment.** Comment only when the WHY is non-obvious: a Unity log quirk, a regex foot-gun, an exit-code contract.
6. **No marketing words** in `--help`, README, or release notes: "Powerful", "Smart", "Seamless", "Enterprise". The tool is a diff utility; describe it as one.
7. **No CHANGELOG entries inline in code.** Use GitHub release notes.
8. **`--help` stays accurate.** Adding a flag without updating `--help` is a regression.

## File Structure
```
unity-build-tool/
├── src/
│   └── builddiff_advanced.py   # Main CLI tool (keep as single file — it's a CLI script)
├── tests/
│   └── fixtures/               # baseline_log.txt, BaseLine_Log2.txt test inputs
├── docs/                       # Usage examples, CLI flag reference
└── .github/workflows/          # CI — run tests on push
```

## Key Files
- `src/builddiff_advanced.py` — the tool itself
- `tests/fixtures/` — test baseline logs
- `wiki/projects/unity-build-tool/unity-build-regression-tool.md` — full code audit + launch path
- `wiki/reference/github-build-regression-tool.md` — GitHub repo audit

## Build & Run
```bash
python src/builddiff_advanced.py --baseline tests/fixtures/baseline_log.txt --compare <new_log>
python -m pytest tests/
```

## Environment Variables
None required for local use.
- Future: `GITHUB_TOKEN` for automated PR comments (via GitHub Actions secret, never hardcoded)

## Code Standards
- Single-file CLI is intentional — keep it simple for users to `curl` and run
- New features: add flags, don't restructure the file
- All test fixtures in `tests/fixtures/`
- `--help` output must stay accurate

## Deploy / Distribution
- GitHub releases with tagged versions
- PyPI publish (future): `python -m build && twine upload`
- GitHub Action: auto-run diff on every PR in Unity repos
