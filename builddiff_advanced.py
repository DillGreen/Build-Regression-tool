from email.mime import base, text
from html import parser
import sys
import json
import re
import argparse
from collections import defaultdict
from unittest import result
import os
from datetime import datetime, UTC
from colorama import init
init()

def format_time(ms):
    seconds = ms / 1000

    if seconds < 60:
        return f"{seconds:.2f}s"

    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f}m"

    hours = minutes / 60
    return f"{hours:.2f}h"

class Color:
    RESET = "\033[0m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"

#========================================
# HISTORY LOGGING
#========================================


def append_to_history(result, filename="build_history.json"):

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "baseline_ms": result["baseline_total_ms"],
        "candidate_ms": result["candidate_total_ms"],
        "delta_ms": result["total_delta_ms"],
        "percent": result["percent_total"],
        "severity": result["severity"],
        "confidence": result["confidence"],
        "reason_code": result["reason_code"]
    }

    if os.path.exists(filename):
        with open(filename, "r") as f:
            history = json.load(f)
    else:
        history = []

    history.append(entry)

    with open(filename, "w") as f:
        json.dump(history, f, indent=2)

#========================================
# HISTORY ANALYSIS/ Trend tracvking
#========================================


def analyze_history(filename="build_history.json"):

    import os
    import json

    if not os.path.exists(filename):
        print("No build history found.")
        return None

    with open(filename, "r") as f:
        history = json.load(f)

    if len(history) < 2:
        print("Not enough history to analyze trends.")
        return None

    import math

    deltas = [entry["delta_ms"] for entry in history]
    percents = [entry["percent"] for entry in history]

    avg_delta = sum(deltas) / len(deltas)
    avg_percent = sum(percents) / len(percents)

    # -------- Linear Regression Slope --------
    n = len(percents)
    x_vals = list(range(n))

    mean_x = sum(x_vals) / n
    mean_y = avg_percent

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, percents))
    denominator = sum((x - mean_x) ** 2 for x in x_vals)

    if denominator == 0:
        slope = 0
    else:
        slope = numerator / denominator

    # -------- Volatility --------
    volatility = max(percents) - min(percents)

    if slope > 3:
        trend_status = "Gradual Drift (Builds Getting Slower)"
    elif slope < -3:
        trend_status = "Recovery Trend (Builds Improving)"
    elif volatility > 50:
        trend_status = "Highly Volatile"
    else:
        trend_status = "Stable"


    return {
        "build_count": n,
        "average_delta_ms": avg_delta,
        "average_percent": avg_percent,
        "slope_percent_per_build": slope,
        "volatility_percent": volatility,
        "trend_status": trend_status
    }






# =========================================
# PARSER
# =========================================

def read_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_last_utp_block(text, block_type="PlayerBuildInfo"):
    blocks = []
    index = 0

    while True:
        start = text.find("##utp:", index)
        if start == -1:
            break

        json_start = text.find("{", start)
        if json_start == -1:
            break

        brace_count = 0
        i = json_start

        while i < len(text):
            if text[i] == "{":
                brace_count += 1
            elif text[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_block = text[json_start:i+1]
                    try:
                        parsed = json.loads(json_block)
                        if parsed.get("type") == block_type:
                            blocks.append(parsed)
                    except:
                        pass
                    break
            i += 1

        index = i

    return blocks[-1] if blocks else None


def extract_number(pattern, text):
    match = re.search(pattern, text)
    return float(match.group(1)) if match else 0.0


def parse_log(path):
    text = read_file(path)

    data = {}


    # UTP Blocks
    player = extract_last_utp_block(text, "PlayerBuildInfo")
    project = extract_last_utp_block(text, "ProjectInfo")

    if player and "duration" in player:
        data["player_build_ms"] = player["duration"]
    else:
        data["player_build_ms"] = 0

    if project:
        data["project_load_s"] = project.get("projectLoad", 0)
        data["asset_refresh_s"] = project.get("assetDatabaseRefresh", 0)
        data["assemblies_load_s"] = project.get("assembliesLoad", 0)
    else:
        data["project_load_s"] = 0
        data["asset_refresh_s"] = 0
        data["assemblies_load_s"] = 0

    # ---- Build Steps Dictionary (REQUIRED) ----
    steps = {}

    # Convert seconds to milliseconds
    steps["Script Compile"] = int(data.get("script_compile_s", 0) * 1000)
    steps["Asset Pipeline Refresh"] = int(data.get("total_refresh_s", 0) * 1000)
    steps["Domain Reload"] = int(data.get("domain_reload_ms", 0))

    # Remove zero entries
    steps = {k: v for k, v in steps.items() if v > 0}

    data["steps"] = steps

    # Script Compilation
    data["script_compile_s"] = extract_number(
        r"AssetDatabase: script compilation time:\s+([0-9.]+)s", text
    )

    # Domain Reload
    data["domain_reload_ms"] = extract_number(
        r"Domain Reload Profiling:\s+([0-9]+)ms", text
    )

    # Asset Pipeline Refresh totals
    refresh_matches = re.findall(
        r"Asset Pipeline Refresh .*? Total: ([0-9.]+) seconds", text
    )
    data["total_refresh_s"] = sum(float(x) for x in refresh_matches)

    # ---- Build Size Extraction ----

    size_match = re.search(r"Total size[:\s]*([\d\.]+)\s*MB", text)
    if size_match:
        data["size_mb"] = float(size_match.group(1))
    else:
        data["size_mb"] = 0.0
    
    # ---- Build Steps Dictionary (required for step regression) ----
    steps = {}

    # These are in seconds in your data -> convert to ms for step comparisons
    if data.get("script_compile_s", 0):
        steps["Script Compile"] = int(float(data["script_compile_s"]) * 1000)

    if data.get("total_refresh_s", 0):
        steps["Asset Pipeline Refresh Total"] = int(float(data["total_refresh_s"]) * 1000)

    # UTP PlayerBuildInfo steps (if available)
    if player and "steps" in player:
        for s in player["steps"]:
            desc = s.get("description", "Unknown Step")
            dur = s.get("duration", 0)  # already ms
            steps[desc] = int(dur)
    data["steps"] = steps
    

    platform_patterns = [
    r"Active build target changed to\s+([A-Za-z0-9_]+)",
    r"Switching build target to\s+([A-Za-z0-9_]+)",
    r"BuildTarget(?:\.|:)\s*([A-Za-z0-9_]+)",
    r"Build target:\s*([A-Za-z0-9_]+)",
    r"Building player for(?: platform)?:\s*([A-Za-z0-9_]+)",
    r"BuildPipeline\.BuildPlayer.*BuildTarget\.([A-Za-z0-9_]+)",
    r"Building for\s+([A-Za-z0-9_]+)",
]

    platform = "Unknown"

    for pattern in platform_patterns:
        match = re.search(pattern, text)
        if match:
            platform = match.group(1).strip()
            break

    data["platform"] = platform


    # ---- Scripting Backend Detection ----
    backend = "Unknown"

    if re.search(r"IL2CPP", text):
        backend = "IL2CPP"
    elif re.search(r"Mono", text):
        backend = "Mono"

    data["scripting_backend"] = backend

    # -------------------------
    # GUARANTEE REQUIRED KEYS
    # -------------------------
    data.setdefault("player_build_ms", 0)
    data.setdefault("steps", {})
    data.setdefault("size_mb", 0.0)
    data.setdefault("platform", "Unknown")
    data.setdefault("scripting_backend", "Unknown")

    # ---- Asset Database Rebuild Detection ----
    if "Rebuilding Library because the asset database could not be found" in text:
        data["asset_db_rebuild"] = True
    else:
        data["asset_db_rebuild"] = False

    return data


# =========================================
# METRICS
# =========================================

def format_data(bytes_val):
    mb = bytes_val / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.2f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"

def analyze_player_steps(base, cand):
    deltas = []
    total_positive = 0

    all_steps = set(base["steps"]) | set(cand["steps"])

    for step in all_steps:
        b = base["steps"].get(step, 0)
        c = cand["steps"].get(step, 0)
        delta = c - b

        if delta > 0:
            total_positive += delta
            deltas.append((step, b, c, delta))

    deltas.sort(key=lambda x: x[3], reverse=True)

    return deltas, total_positive

def calculate_regression_score(percent):
    if percent < 5:
        return 2
    elif percent < 15:
        return 4
    elif percent < 25:
        return 6
    elif percent < 40:
        return 8
    else:
        return 10

def analyze_build(base, cand):

    result = {}

    required = ["steps"]
    for k in required:
        if k not in base or k not in cand:
            raise KeyError(f"Missing required key '{k}' in synthetic/log parse output")

    # ---- Core Build Time Calculations ----
    baseline_total_ms = base.get("player_build_ms", 0)
    candidate_total_ms = cand.get("player_build_ms", 0)

    total_delta_ms = candidate_total_ms - baseline_total_ms

    percent_total = (
        (total_delta_ms / baseline_total_ms) * 100
        if baseline_total_ms else 0
    )

    result["baseline_total_ms"] = baseline_total_ms
    result["candidate_total_ms"] = candidate_total_ms
    result["total_delta_ms"] = total_delta_ms
    result["percent_total"] = percent_total

    # Step analysis
    deltas, total_positive = analyze_player_steps(base, cand)

    # SORT largest regression first
    deltas = sorted(deltas, key=lambda x: x[3], reverse=True)

    # ---- Build Size Delta ----
    baseline_size = base.get("size_mb", 0.0)
    candidate_size = cand.get("size_mb", 0.0)

    size_delta_mb = candidate_size - baseline_size

    result["baseline_size_mb"] = baseline_size
    result["candidate_size_mb"] = candidate_size
    result["size_delta_mb"] = size_delta_mb

    contributors = []

    for step, b, c, delta in deltas:
        if delta > 0:
            contributors.append({
                "step": step,
                "baseline_ms": b,
                "candidate_ms": c,
                "delta_ms": delta,
                "contribution_percent": (delta / total_positive) * 100 if total_positive else 0
            })

    result["contributors"] = contributors
    result["top_3"] = contributors[:3]

    abs_percent = abs(percent_total)

    if abs_percent < 5:
        severity = "Not Significant"
    elif abs_percent < 15:
        severity = "Minor Regression"
    elif abs_percent < 40:
        severity = "Moderate Regression"
    else:
        severity = "Major Regression"

    result["baseline_size_mb"] = base.get("size_mb", 0.0)
    result["candidate_size_mb"] = cand.get("size_mb", 0.0)
    result["size_delta_mb"] = result["candidate_size_mb"] - result["baseline_size_mb"]
    result["severity"] = severity

    if contributors:
        dominant_share = contributors[0]["contribution_percent"]
        dominant_step = contributors[0]["step"]
            # Confidence classification based on dominant step's contribution
        if dominant_share >= 85:
            confidence = "Very High"
        elif dominant_share >= 70:
            confidence = "High"
        elif dominant_share >= 50:
            confidence = "Medium"
        else:
            confidence = "Low"

        result["confidence"] = confidence
        result["reason_code"] = (
            f"DOMINANT_STEP_{dominant_step.replace(' ', '_').upper()}"
        )
        result["dominant_share"] = dominant_share

    else:
        result["confidence"] = "Low"
        result["reason_code"] = "NO_SIGNIFICANT_REGRESSION"
        result["dominant_share"] = 0

    # Primary Driver
    if contributors and result["dominant_share"] >= 40:
        result["primary_driver"] = contributors[0]["step"]
    else:
        result["primary_driver"] = "Distributed Multi-Factor Regression"
    
    # Caching regression detection
    script_compile_delta = next(
        (c["delta_ms"] for c in contributors 
        if "Script Compile" in c["step"]), 0
    )

    if script_compile_delta > 5000 and result["percent_total"] < 40:
        result["caching_regression"] = True
    else:
        result["caching_regression"] = False


    # Platform/Backend switch detection
    baseline_backend = base.get("scripting_backend", "Unknown")
    candidate_backend = cand.get("scripting_backend", "Unknown")

    result["backend_switch"] = (
        baseline_backend != candidate_backend
        and baseline_backend != "Unknown"
        and candidate_backend != "Unknown"
    )

    result["baseline_backend"] = baseline_backend
    result["candidate_backend"] = candidate_backend
    # Platform switch detection
    baseline_platform = base.get("platform", "Unknown")
    candidate_platform = cand.get("platform", "Unknown")

    result["platform_switch"] = (
        baseline_platform != candidate_platform
        and baseline_platform != "Unknown"
        and candidate_platform != "Unknown"
    )

    result["baseline_platform"] = baseline_platform
    result["candidate_platform"] = candidate_platform

    diagnosis = diagnose_regression(result)
    result["diagnosis"] = diagnosis

    return result

def classify_build_type(percent):
    if percent < 5:
        return "Small Incremental Build"
    elif percent < 20:
        return "Moderate Change Build"
    else:
        return "Large Change Build"   

def classify_step_category(step_name):
    name = step_name.lower()

    if "script" in name or "assembly" in name:
        return "SCRIPT"
    elif "asset" in name or "resource" in name:
        return "ASSET"
    elif "postprocess" in name or "write" in name:
        return "PACKAGING"
    else:
        return "OTHER"

# =========================================
# REPORT
# =========================================

def print_report(result):

    total_delta = result["total_delta_ms"]
    percent = result["percent_total"]
    contributors = result.get("contributors", [])[:3]
    severity = result["severity"]
    score = calculate_regression_score(percent)
    build_type = classify_build_type(percent)

    print("\n================ BUILD REGRESSION SUMMARY ================\n")

    print(f"Baseline Build:  {format_time(result['baseline_total_ms'])}")
    print(f"Candidate Build: {format_time(result['candidate_total_ms'])}")
    print(f"Total Change:    {format_time(abs(total_delta))} ({percent:+.1f}%)")
        # ----- Severity Color Mapping -----
    severity_text = result["severity"]

    if severity_text == "Major Regression":
        severity_colored = f"{Color.RED}{severity_text}{Color.RESET}"
    elif severity_text == "Moderate Regression":
        severity_colored = f"{Color.YELLOW}{severity_text}{Color.RESET}"
    elif severity_text == "Minor Regression":
        severity_colored = f"{Color.CYAN}{severity_text}{Color.RESET}"
    elif severity_text == "Not Significant":
        severity_colored = f"{Color.GREEN}{severity_text}{Color.RESET}"
    else:
        severity_colored = severity_text
    print(f"Severity:        {severity_colored}")
    print(f"Regression Score: {score}/10")
    print(f"Build Type:      {build_type}")
    print(f"Baseline Backend:   {result.get('baseline_backend')}")
    print(f"Candidate Backend:  {result.get('candidate_backend')}")
    print(f"Baseline Platform:  {result.get('baseline_platform')}")
    print(f"Candidate Platform: {result.get('candidate_platform')}")
    if result.get("baseline_size_mb", 0) > 0 or result.get("candidate_size_mb", 0) > 0:
        print(f"Baseline Size:  {result['baseline_size_mb']:.2f} MB")
        print(f"Candidate Size: {result['candidate_size_mb']:.2f} MB")
        print(f"Size Change:    {result['size_delta_mb']:+.2f} MB")
    print("\n---------------- TOP CONTRIBUTORS ----------------\n")

    if not contributors:
        print("No significant regression contributors detected.\n")
    else:
        for contributor in contributors[:5]:
            print(f"{contributor['step']}")
            print(f"  Time Increase: {format_time(contributor['delta_ms'])}")
            print(f"  Contribution:  {contributor['contribution_percent']:.1f}%")
            if "data_delta_bytes" in contributor:
                print(f"  Data Increase: {format_data(contributor['data_delta_bytes'])}")
            print()

    print("-----------------------------------------------------------\n")

    if result["dominant_share"] >= 40:
        print(f"Primary Regression Driver: {result['primary_driver']}")
    else:
        print("Primary Regression Driver: Distributed / Multi-Factor")

    print(f"Reason Code: {result['reason_code']}")
    print(f"Confidence:  {result['confidence']}")

    print("\n---------------- DIAGNOSTIC ANALYSIS ----------------\n")

    diag = result.get("diagnosis", {})

    print(f"Root Classification: {diag.get('code', 'N/A')}")
    print(f"Primary Cause: {diag.get('cause', 'N/A')}")
    print(f"Likely Reason: {diag.get('likely_reason', 'N/A')}")
    print(f"Suggested Fix: {diag.get('suggested_fix', 'N/A')}")


    print("\n---------------- INCIDENT RESPONSE ----------------\n")

    diag = result.get("diagnosis", {})

    print(f"Owner To Ping: {diag.get('owner', 'N/A')}")
    print(f"Confidence Reason: {diag.get('confidence_why', 'N/A')}")

    print("\nImmediate Next Actions:")
    for action in diag.get("next_actions", []):
        print(f" - {action}")

    if result.get("caching_regression"):
        print("\n⚠️ Cache invalidation suspected")

    if result.get("platform_switch"):
        print("\n⚠️ Platform mismatch detected")
    print("\n===========================================================\n")

def diagnose_regression(result):
    dominant_raw = result.get("primary_driver", "") or ""
    dominant = dominant_raw.strip().lower()
    size_delta = abs(result.get("size_delta_mb", 0))
    dominant_share = result.get("dominant_share", 0)
    percent = abs(result.get("percent_total", 0))
    diagnosis = {}

    # --- Highest Priority Checks ---

    if result.get("backend_switch"):
        diagnosis["code"] = "SCRIPTING_BACKEND_SWITCH"
        diagnosis["cause"] = "Scripting backend changed (Mono ↔ IL2CPP)"
        diagnosis["likely_reason"] = (
            f"Baseline: {result.get('baseline_backend')} "
            f"vs Candidate: {result.get('candidate_backend')}"
        )
        diagnosis["suggested_fix"] = "Ensure scripting backend remains consistent for valid comparison"
        pass

    elif result.get("platform_switch"):
        diagnosis["code"] = "PLATFORM_SWITCH"
        diagnosis["cause"] = "Build target platform changed"
        diagnosis["likely_reason"] = (
            f"Baseline: {result.get('baseline_platform')} "
            f"vs Candidate: {result.get('candidate_platform')}"
        )
        diagnosis["suggested_fix"] = "Ensure build target platform is consistent"
        pass

    elif result.get("asset_db_rebuild"):
        diagnosis["code"] = "ASSET_DATABASE_REBUILD"
        diagnosis["cause"] = "Unity rebuilt the entire Library/ asset database"
        diagnosis["likely_reason"] = "Library folder missing, corrupted, or cache invalidated"
        diagnosis["suggested_fix"] = "Ensure Library folder persists between builds; avoid deleting or cleaning it"

    elif result.get("caching_regression"):
        diagnosis["code"] = "CACHE_INVALIDATION"
        diagnosis["cause"] = "Incremental build cache likely invalidated"
        diagnosis["likely_reason"] = "Library cache cleared or assembly hash changed"
        diagnosis["suggested_fix"] = "Check for GUID changes or full rebuild triggers"
        pass

    # --- Dominant Step Classification ---

    elif "writing asset file" in dominant:
        if size_delta > 50:
            diagnosis["code"] = "ASSET_CONTENT_EXPANSION"
            diagnosis["cause"] = "Large increase in build content size"
            diagnosis["likely_reason"] = "New textures, models, audio, or build-included assets added"
            diagnosis["suggested_fix"] = "Review recent asset commits and compression/import settings"
        else:
            diagnosis["code"] = "ASSET_SERIALIZATION_OVERHEAD"
            diagnosis["cause"] = "Asset reimport or cache invalidation"
            diagnosis["likely_reason"] = "Asset database refresh or GUID remapping triggered"
            diagnosis["suggested_fix"] = "Check Library cache invalidation or asset GUID changes"
        pass

    elif "produceplayerscriptassemblies" in dominant:
        diagnosis["code"] = "SCRIPT_RECOMPILATION_SPIKE"
        diagnosis["cause"] = "Increased C# compile time"
        diagnosis["likely_reason"] = "Large code refactor or assembly definition change"
        diagnosis["suggested_fix"] = "Review asmdef changes and recent script growth"
        pass

    elif "postprocess built player" in dominant:
        diagnosis["code"] = "POSTPROCESSING_PIPELINE_EXPANSION"
        diagnosis["cause"] = "Post-build pipeline slowed"
        diagnosis["likely_reason"] = "New build hooks, IL2CPP changes, or build callbacks added"
        diagnosis["suggested_fix"] = "Inspect build scripts and post-build automation"
        pass

    else:    # --- Fallback ---
        diagnosis["code"] = "UNKNOWN_REGRESSION_PATTERN"
        diagnosis["cause"] = "Regression detected but pattern unclear"
        diagnosis["likely_reason"] = "Distributed or multi-factor regression"
        diagnosis["suggested_fix"] = "Review commits between baseline and candidate builds"

    print(f"DEBUG dominant = '{dominant}'")
    print("DEBUG dominant_raw =", repr(dominant_raw))
    print("DEBUG dominant_norm =", repr(dominant))
    print("DEBUG size_delta_mb =", size_delta)
    print("DEBUG backend_switch =", result.get("backend_switch"))
    print("DEBUG platform =", result.get("baseline_platform"), result.get("candidate_platform"))
    # ==============================
    # ENRICHMENT (THIS IS WHAT YOU WANTED BACK)
    # ==============================

    # ---- Always attach incident response fields ----
    diagnosis["owner"] = determine_owner(dominant)

    # why the confidence is what it is (based on share)
    if dominant_share >= 85:
        diagnosis["confidence_why"] = "Single step dominates regression (>85%)"
    elif dominant_share >= 70:
        diagnosis["confidence_why"] = "Top step is a strong driver (70–85%)"
    elif dominant_share >= 50:
        diagnosis["confidence_why"] = "Top step is meaningful but not dominant (50–70%)"
    else:
        diagnosis["confidence_why"] = "No clear single driver (<50%)"

    diagnosis["next_actions"] = immediate_actions(diagnosis.get("code", "UNKNOWN"))

    return diagnosis
    

def determine_owner(dominant_step):
    if "writing asset files" in dominant_step:
        return "Content / Art Team"
    elif "produceplayerscriptassemblies" in dominant_step:
        return "Gameplay / Engineering Team"
    elif "postprocess built player" in dominant_step:
        return "Build Engineering / DevOps"
    elif "domain reload" in dominant_step:
        return "Core Engineering"
    else:
        return "Cross-Team Investigation"


def immediate_actions(code):
    if code == "ASSET_CONTENT_EXPANSION":
        return [
            "Check recent large asset commits",
            "Verify texture compression settings",
            "Audit asset bundle size growth"
        ]
    elif code == "SCRIPT_RECOMPILATION_SPIKE":
        return [
            "Review recent asmdef changes",
            "Check large code merges",
            "Inspect incremental compile invalidation"
        ]
    elif code == "POSTPROCESSING_PIPELINE_EXPANSION":
        return [
            "Review build hooks and post-build scripts",
            "Check IL2CPP configuration changes"
        ]
    elif code == "ASSET_SERIALIZATION_OVERHEAD":
        return [
            "Check if Library folder was deleted",
            "Verify no meta/GUID churn occurred",
            "Inspect asset database refresh triggers",
            "Confirm incremental build was not invalidated"
        ]
    else:
        return [
            "Review commits between baseline and candidate",
            "Inspect build pipeline changes"
        ]

# =========================================
# MAIN CLI
# =========================================

def run_synthetic_test():

    # Create synthetic baseline and candidate dictionaries
    baseline = {
        "player_build_ms": 120000,
        "steps": {
            "Writing asset files": 60000,
            "ProducePlayerScriptAssemblies": 15000,
            "Postprocess built player": 10000,
        },
        "size_mb": 500.0,
        "platform": "StandaloneWindows64",
        "scripting_backend": "Mono",
        "asset_db_rebuild": False,
    }

    candidate = {
        "player_build_ms": 240000,
        "steps": {
            "Writing asset files": 180000,
            "ProducePlayerScriptAssemblies": 18000,
            "Postprocess built player": 15000,
        },
        "size_mb": 500.0,
        "platform": "StandaloneWindows64",
        "scripting_backend": "Mono",
        "asset_db_rebuild": False,
    }

    result = analyze_build(baseline, candidate)
    print_report(result)

    append_to_history(result)
    print("Synthetic result appended to history.")



def generate_markdown_report(result):

    lines = []
    lines.append("## 🚀 Build Regression Report\n")

    lines.append(f"**Baseline Build:** {result['baseline_total_ms']/1000:.2f}s  ")
    lines.append(f"**Candidate Build:** {result['candidate_total_ms']/1000:.2f}s  ")

    total_delta = result["total_delta_ms"]
    percent_total = result["percent_total"]
    sign = "+" if total_delta >= 0 else "-"

    lines.append(f"**Total Delta:** {sign}{abs(total_delta)/1000:.2f}s "
                 f"({sign}{abs(percent_total):.1f}%)  ")

    lines.append(f"**Severity:** {result['severity']}  ")
    lines.append(f"**Confidence:** {result['confidence']}  ")
    lines.append(f"**Reason Code:** `{result['reason_code']}`\n")

    if result["contributors"]:
        lines.append("### 🔎 Top Contributors\n")
        lines.append("| Step | Baseline | Candidate | Delta | Contribution |")
        lines.append("|------|----------|----------|--------|--------------|")

        for c in result["contributors"][:5]:
            lines.append(
                f"| {c['step']} | "
                f"{c['baseline_ms']/1000:.2f}s | "
                f"{c['candidate_ms']/1000:.2f}s | "
                f"+{c['delta_ms']/1000:.2f}s | "
                f"{c['contribution_percent']:.1f}% |"
            )

    return "\n".join(lines)


def main():

    parser = argparse.ArgumentParser(
        description="Unity Build Regression Analyzer"
    )
    parser.add_argument("baseline", nargs="?", help="Baseline log file")
    parser.add_argument("candidate", nargs="?", help="Candidate log file")
    parser.add_argument("--synthetic", action="store_true", 
                        help="Run synthetic test case")
    parser.add_argument("--json", action="store_true", 
                        help="Output JSON instead of text")
    parser.add_argument("--ci", action="store_true",
                    help="Fail with exit code if regression exceeds threshold")
    parser.add_argument("--markdown", action="store_true",
                    help="Output Markdown report")
    parser.add_argument("--track", action="store_true",
                    help="Append result to build history")
    parser.add_argument("--fail-percent", type=float, default=40,
                    help="Percent threshold to fail CI")
    parser.add_argument("--fail-seconds", type=float, default=30,
                    help="Absolute seconds threshold to fail CI")
    parser.add_argument("--history", action="store_true",
                    help="Analyze historical build trends")




    args = parser.parse_args()

# 1 Histrical trend analysis mode
    if args.history:
        trend = analyze_history()
        if trend:
            print("\n===== HISTORICAL TREND ANALYSIS =====\n")
            print(f"Build Count: {trend['build_count']}")
            avg_seconds = trend['average_delta_ms'] / 1000
            avg_minutes = avg_seconds / 60
            avg_hours = avg_minutes / 60

            print("Average Delta:")
            print(f"  {format_time(trend['average_delta_ms'])}")


            print(f"Average Percent: {trend['average_percent']:.2f}%")
            print(f"Slope: {trend['slope_percent_per_build']:.2f}% per build")
            print(f"Volatility: {trend['volatility_percent']:.2f}%")
            print(f"Trend Classification: {trend['trend_status']}")


        return

# 2 Synthetic test mode
    if args.synthetic:
        run_synthetic_test()
        return

    if not args.baseline or not args.candidate:
        print("Usage: python builddiff_advanced.py baseline.log candidate.log")
        return

    base = parse_log(args.baseline)
    cand = parse_log(args.candidate)

    analysis = analyze_build(base, cand)

    # Output modes
    if args.json:
        print(json.dumps(analysis, indent=2))
    elif args.markdown:
        print(generate_markdown_report(analysis))
    else:
        print_report(analysis)

    # History tracking
    if args.track:
        append_to_history(analysis)
        print("Result appended to build history.")

    # CI Guard
    if args.ci:
        import sys
        percent = analysis["percent_total"]
        seconds = abs(analysis["total_delta_ms"]) / 1000

        if percent >= args.fail_percent or seconds >= args.fail_seconds:
            print("CI GUARD: Threshold exceeded.")
            sys.exit(1)
        else:
            sys.exit(0)




     
if __name__ == "__main__":
    main()
