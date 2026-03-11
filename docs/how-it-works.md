# How It Works

Build Regression Tool compares two Unity build logs and helps explain why one build became slower than another.

## Parsing
The tool reads Unity build logs and extracts important build information such as:
- total build duration
- build step timing data
- scripting backend
- platform when available
- build size when available
- asset database rebuild signals
- parse warnings and log quality

## Step Comparison
The tool compares the baseline log and the candidate log step by step. It calculates:
- total build delta
- percent change
- step timing differences
- contribution percentage for regressed steps

## Noise Control
To reduce false positives, the tool:
- ignores very small step changes
- ignores very low-share contributors
- uses percent and time thresholds
- supports history-aware checks for unusual slowdowns

## Diagnosis
The tool classifies likely causes such as:
- asset serialization overhead
- asset database rebuild
- cache invalidation
- scripting backend switch
- platform switch
- script compilation spikes
- post-processing slowdowns

## Reporting
The tool can generate:
- terminal text reports
- JSON output
- Markdown reports
- HTML reports

## CI Usage
The tool can run in CI pipelines to compare builds automatically and catch meaningful regressions early.
