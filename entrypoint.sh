#!/bin/bash
set -e

# Change to the GitHub workspace so relative paths resolve correctly.
# WORKDIR in the Dockerfile is /app; GitHub mounts the runner workspace at
# /github/workspace and sets GITHUB_WORKSPACE accordingly.
cd "${GITHUB_WORKSPACE:-/github/workspace}"

BASELINE_LOG="$1"
CANDIDATE_LOG="$2"
FAIL_PERCENT="${3:-40}"
FAIL_SECONDS="${4:-30}"
OUTPUT_FORMAT="${5:-markdown}"
HTML_REPORT_PATH="${6:-build_regression_report.html}"
TRACK_HISTORY="${7:-false}"
PLATFORM="$8"
BUILD_OUTPUT_PATH="$9"

# Validate required inputs
if [ -z "$BASELINE_LOG" ] || [ -z "$CANDIDATE_LOG" ]; then
  echo "ERROR: baseline_log and candidate_log are required inputs."
  exit 1
fi

if [ ! -f "$BASELINE_LOG" ]; then
  echo "ERROR: Baseline log file not found: $BASELINE_LOG"
  exit 1
fi

if [ ! -f "$CANDIDATE_LOG" ]; then
  echo "ERROR: Candidate log file not found: $CANDIDATE_LOG"
  exit 1
fi

# Build the command
CMD="python /app/builddiff_advanced.py $BASELINE_LOG $CANDIDATE_LOG"
CMD="$CMD --ci"
CMD="$CMD --fail-percent $FAIL_PERCENT"
CMD="$CMD --fail-seconds $FAIL_SECONDS"

# Output format
if [ "$OUTPUT_FORMAT" = "json" ]; then
  CMD="$CMD --json"
elif [ "$OUTPUT_FORMAT" = "markdown" ]; then
  CMD="$CMD --markdown"
elif [ "$OUTPUT_FORMAT" = "html" ]; then
  CMD="$CMD --html --html-out $HTML_REPORT_PATH"
fi

# Optional flags
if [ "$TRACK_HISTORY" = "true" ]; then
  CMD="$CMD --track"
fi

if [ -n "$PLATFORM" ]; then
  CMD="$CMD --platform $PLATFORM"
fi

if [ -n "$BUILD_OUTPUT_PATH" ]; then
  CMD="$CMD --build-output $BUILD_OUTPUT_PATH"
fi

echo "Running: $CMD"
echo ""

# Run and capture output + exit code
set +e
OUTPUT=$(eval $CMD 2>&1)
EXIT_CODE=$?
set -e

echo "$OUTPUT"

# Parse outputs for GitHub Actions
if echo "$OUTPUT" | grep -q "regression_detected="; then
  REGRESSION=$(echo "$OUTPUT" | grep "regression_detected=" | cut -d= -f2)
  echo "regression_detected=$REGRESSION" >> $GITHUB_OUTPUT
else
  if [ $EXIT_CODE -ne 0 ]; then
    echo "regression_detected=true" >> $GITHUB_OUTPUT
  else
    echo "regression_detected=false" >> $GITHUB_OUTPUT
  fi
fi

# Extract severity if present in output
SEVERITY=$(echo "$OUTPUT" | grep -i "Severity:" | head -1 | sed 's/.*Severity: *//' | tr -d '[:space:]' | head -c 20 || echo "Unknown")
echo "severity=$SEVERITY" >> $GITHUB_OUTPUT

# Extract reason code if present
REASON=$(echo "$OUTPUT" | grep -i "Reason Code:" | head -1 | sed 's/.*Reason Code: *//' | tr -d '[:space:]' | head -c 60 || echo "UNKNOWN")
echo "reason_code=$REASON" >> $GITHUB_OUTPUT

# Extract percent change if present
PERCENT=$(echo "$OUTPUT" | grep -i "Total Change:" | head -1 | grep -o '[+-][0-9.]*%' | head -1 || echo "0%")
echo "percent_change=$PERCENT" >> $GITHUB_OUTPUT

# Summary line
if [ $EXIT_CODE -ne 0 ]; then
  echo "summary=Regression detected — severity: $SEVERITY, reason: $REASON" >> $GITHUB_OUTPUT
else
  echo "summary=No regression detected" >> $GITHUB_OUTPUT
fi

exit $EXIT_CODE
