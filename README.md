# Build-Regression-tool
# Build Regression Tool

Build Regression Tool is a lightweight Python CLI that helps explain why a Unity build became slower.

It compares two Unity build logs, measures the total build change, finds the pipeline steps that increased the most, and classifies likely causes such as asset database rebuilds, cache invalidation, platform changes, scripting backend changes, asset expansion, or script compilation spikes.

The tool can generate clear text, JSON, Markdown, and HTML reports for local debugging or CI pipelines. It also includes noise control to reduce false positives from normal build variation, plus history-aware checks to better detect real regressions over time.

## Features

- Compare two Unity build logs
- Rank the top regression contributors
- Detect likely causes of build slowdowns
- Reduce false positives with noise filtering
- Support history-aware regression checks
- Generate text, JSON, Markdown, and HTML reports
- Work in local workflows or CI pipelines
- Support synthetic test mode for validation

## Project Structure

- `builddiff_advanced.py` — main CLI tool
- `docs/` — usage, examples, and CI integration notes
- `tests/` — parser, analysis, and synthetic tests
- `tests/sample_logs/` — sample Unity build logs used for testing

## Installation
pip install -r requirements.txt
### Basic usage

## Basic Usage
  Compare two logs:
  python builddiff_advanced.py baseline_log.txt candidate_log.txt  (These are example names for logs)

Generate JSON:
  python builddiff_advanced.py baseline_log.txt candidate_log.txt --json

Generate Markdown:
  python builddiff_advanced.py baseline_log.txt candidate_log.txt --markdown

Generate HTML:
  python builddiff_advanced.py baseline_log.txt candidate_log.txt --html --html-out report.html

Run synthetic validation:
  python builddiff_advanced.py --synthetic

Analyze history: 
  python builddiff_advanced.py --history


### CI usage


## CI Usage

This tool can be used in CI pipelines to compare a new Unity build against a baseline and flag meaningful regressions early.

Example:

python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci


### Limitations

```md
## Limitations

- Platform detection depends on log contents unless passed through CLI
- Build size detection is most reliable when a build output path is provided
- History-based checks are more useful after multiple real runs
- Some Unity log formats may vary between versions



