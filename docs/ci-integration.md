# CI Integration

Build Regression Tool can be used in CI pipelines to catch Unity build slowdowns early.

## Why use it in CI

Instead of finding build regressions later, teams can compare a new build against a baseline automatically after each build and review a report right away.

This helps teams:
- catch slower builds earlier
- understand what changed
- identify the biggest contributors
- decide who should investigate
- archive reports for later review

## Basic CI Flow

A simple CI workflow can look like this:

1. Run the baseline Unity build
2. Run the candidate Unity build
3. Save both build logs
4. Run Build Regression Tool against the two logs
5. Generate a report
6. Fail CI if thresholds are exceeded

## Example CLI Command

```bash
python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci

CI with HTML Report
python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci --html --html-out report.html

CI Custom Threshold
python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci --fail-percent 40 --fail-seconds 30

Platform Override
(This helps when the Unity logs do not clearly contain platform information)
python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci --fail-percent 40 --fail-seconds 30


