from email.mime import base, text
from html import parser
from logging import warn
from logging import warn
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


def load_history_values(filename="build_history.json"):
    if not os.path.exists(filename):
        return []

    with open(filename, "r") as f:
        history = json.load(f)

    return [entry["candidate_ms"] for entry in history if "candidate_ms" in entry]



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

    data = {"steps": {},
            "player_build_ms": 0,
            "size_mb": 0.0,
            "platform": "Unknown",
            "scripting_backend": "Unknown",
            "asset_db_rebuild": False,
            "parse_warnings": []
            }
    def warn(msg):
        data["parse_warnings"].append(msg)

    # UTP Blocks
    player = extract_last_utp_block(text, "PlayerBuildInfo")
    project = extract_last_utp_block(text, "ProjectInfo")

    if not player:
        warn("PlayerBuildInfo block missing")
    if not project:
        warn("ProjectInfo block missing")

    if player and "duration" in player:
        try:
            data["player_build_ms"] = int(player["duration"])
        except Exception:
            warn("Failed to parse player build duration")
            data["player_build_ms"] = 0
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
        r"WindowsStandaloneSupport",
        r"AndroidPlayer",
        r"WebGLSupport",
        r"iOSSupport",
    ]

    platform = "Unknown"

    for pattern in platform_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.groups():
                platform = match.group(1).strip()
            else:
                token = pattern.lower()
                if "windowsstandalonesupport" in token:
                    platform = "StandaloneWindows64"
                elif "androidplayer" in token:
                    platform = "Android"
                elif "webglsupport" in token:
                    platform = "WebGL"
                elif "iossupport" in token:
                    platform = "iOS"
            break

    data["platform"] = platform


    # ---- Scripting Backend Detection ----
    backend = "Unknown"

    if re.search(r"il2cpp", text, re.IGNORECASE):
        backend = "IL2CPP"
    elif re.search(r"\bmono\b", text, re.IGNORECASE):
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

    if "Build completed with a result" not in text and "Build Finished" not in text:
        data["log_truncated"] = True
        warn("Log may be truncated or incomplete")
    else:
        data["log_truncated"] = False

    score = 100

    if not data["steps"]:
        score -= 40

    if data["player_build_ms"] == 0:
        score -= 40

    if data["platform"] == "Unknown":
        score -= 10

    if data["size_mb"] == 0:
        score -= 10

    data["parse_quality_score"] = max(score, 0)

    if score >= 80:
        data["parse_quality"] = "HIGH"
    elif score >= 50:
        data["parse_quality"] = "MEDIUM"
    else:
        data["parse_quality"] = "LOW"


    if not data["steps"]:
        warn("No build steps parsed from log")

    return data


# =========================================
# METRICS
# =========================================

# Stablize incremental build regression detection by applying EWMA smoothing and robust std dev outlier detection to historical data. This helps reduce noise from individual builds and identify true regressions.
def ewma(values, alpha=0.3):
    m = None
    for v in values:
        m = v if m is None else (alpha * v + (1 - alpha) * m)
    return m

def robust_std(values):
    # cheap robust: MAD * 1.4826
    if not values:
        return 0.0
    med = sorted(values)[len(values)//2]
    dev = [abs(x - med) for x in values]
    mad = sorted(dev)[len(dev)//2]
    return mad * 1.4826
# Stablize incremental build regression detection by applying EWMA smoothing and robust std dev outlier detection to historical data. This helps reduce noise from individual builds and identify true regressions.

def format_data(bytes_val):
    mb = bytes_val / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.2f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


def get_build_size_mb(path):
    if not path:
        return 0.0

    if os.path.isfile(path):
        return os.path.getsize(path) / (1024 * 1024)

    if os.path.isdir(path):
        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total / (1024 * 1024)

    return 0.0

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

    result["parse_warnings"] = base.get("parse_warnings", []) + cand.get("parse_warnings", [])
    result["parse_quality_score"] = min(
        base.get("parse_quality_score", 100),
        cand.get("parse_quality_score", 100)
    )

    score = result["parse_quality_score"]

    if score >= 80:
        result["parse_quality"] = "HIGH"
    elif score >= 50:
        result["parse_quality"] = "MEDIUM"
    else:
        result["parse_quality"] = "LOW"

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
    result["asset_db_rebuild"] = base.get("asset_db_rebuild") or cand.get("asset_db_rebuild")


    history_values = load_history_values()

    if len(history_values) >= 3:
        expected_ms = ewma(history_values)
        sigma_ms = robust_std(history_values)

        result["history_expected_ms"] = expected_ms
        result["history_sigma_ms"] = sigma_ms

        if sigma_ms > 0:
            result["history_zscore"] = (candidate_total_ms - expected_ms) / sigma_ms
        else:
            result["history_zscore"] = 0
    else:
        result["history_expected_ms"] = None
        result["history_sigma_ms"] = None
        result["history_zscore"] = None


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

    MIN_STEP_MS = 2000      # ignore <2s changes
    MIN_STEP_SHARE = 2.0    # ignore <2% contributors

    for step, b, c, delta in deltas:

        if delta <= 0:
            continue

        if delta < MIN_STEP_MS:
            continue

        share = (delta / total_positive) * 100 if total_positive else 0

        if share < MIN_STEP_SHARE:
            continue

        contributors.append({
            "step": step,
            "baseline_ms": b,
            "candidate_ms": c,
            "delta_ms": delta,
            "contribution_percent": share
        })
    result["contributors"] = contributors
    result["top_3"] = contributors[:3]
    top3_share = sum(c["contribution_percent"] for c in contributors[:3]) if contributors else 0
    result["top3_share"] = top3_share

    abs_percent = abs(percent_total)

    dominant_delta_ms = contributors[0]["delta_ms"] if contributors else 0
    dominant_share = contributors[0]["contribution_percent"] if contributors else 0

    regression_detected, gate_reason = is_regression(
        percent_total,
        total_delta_ms,
        dominant_delta_ms,
        dominant_share
    )

    result["regression_detected"] = regression_detected
    result["regression_gate_reason"] = gate_reason

    if result["regression_detected"]:
        if contributors and result["top3_share"] < 50 and abs(percent_total) < 15:
            result["regression_detected"] = False
            result["regression_gate_reason"] = "DIFFUSE_NOISE_SUPPRESSED"

    if result["history_zscore"] is not None and result["history_zscore"] >= 2.5:
        result["regression_detected"] = True
        result["regression_gate_reason"] = "HISTORY_ZSCORE_OVERRIDE"

    if not regression_detected:
        severity = "Not Significant"
    else:
        if abs_percent < 15:
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

    if not contributors:
        result["contributors"] = []
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
    if result.get("history_expected_ms") is not None:
        print(f"Expected Build (history): {format_time(result['history_expected_ms'])}")
        print(f"History Z-Score:          {result.get('history_zscore', 0):.2f}")
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
    

def is_regression(percent_total: float, total_delta_ms: int, dominant_delta_ms: int, dominant_share: float,
                  pct_gate=10.0, sec_gate=15.0, ignore_pct=5.0, dominant_sec_override=30.0, dominant_share_override=70.0):
    delta_s = abs(total_delta_ms) / 1000.0
    if abs(percent_total) < ignore_pct:
        return False, "IGNORE_BAND"
    if abs(percent_total) >= pct_gate and delta_s >= sec_gate:
        return True, "PCT_AND_SEC"
    if (dominant_delta_ms / 1000.0) >= dominant_sec_override and dominant_share >= dominant_share_override:
        return True, "DOMINANT_STEP_OVERRIDE"
    # soft drift (5–10%) only counts if absolute time is meaningful
    if abs(percent_total) >= ignore_pct and delta_s >= sec_gate:
        return True, "SEC_GATE"
    return False, "NOISE"

def determine_owner(dominant_step):
    dominant_step = dominant_step.lower()
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


def generate_html_report(result):
    import html

    def esc(x):
        return html.escape(str(x))

    sev = result.get("severity", "Unknown")
    sev_class = {
        "Major Regression": "sev-major",
        "Moderate Regression": "sev-moderate",
        "Minor Regression": "sev-minor",
        "Not Significant": "sev-ok",
    }.get(sev, "sev-unknown")

    diag = result.get("diagnosis", {})
    contributors = result.get("contributors", [])[:5]
    warnings = result.get("parse_warnings", [])

    rows = ""
    if contributors:
        for c in contributors:
            rows += f"""
            <tr>
              <td>{esc(c['step'])}</td>
              <td>{esc(format_time(c['baseline_ms']))}</td>
              <td>{esc(format_time(c['candidate_ms']))}</td>
              <td>{esc(format_time(c['delta_ms']))}</td>
              <td>{esc(f"{c['contribution_percent']:.1f}%")}</td>
            </tr>
            """
    else:
        rows = "<tr><td colspan='5'>No significant contributors</td></tr>"

    warning_html = "".join(f"<li>{esc(w)}</li>" for w in warnings) if warnings else "<li>None</li>"
    next_actions = "".join(f"<li>{esc(a)}</li>" for a in diag.get("next_actions", [])) or "<li>None</li>"

    return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>Build Regression Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    :root {{
        --bg: #f5f7fb;
        --card: #ffffff;
        --card-border: #d9e0ea;
        --text: #18212f;
        --muted: #5f6b7a;
        --accent: #2563eb;
        --accent-soft: #dbeafe;

        --major-bg: #fee2e2;
        --major-text: #b91c1c;

        --moderate-bg: #fef3c7;
        --moderate-text: #92400e;

        --minor-bg: #dbeafe;
        --minor-text: #1d4ed8;

        --ok-bg: #dcfce7;
        --ok-text: #166534;

        --unknown-bg: #e5e7eb;
        --unknown-text: #374151;

        --table-head: #eef2f7;
        --shadow: 0 8px 24px rgba(16, 24, 40, 0.06);
    }}

    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg: #0f172a;
            --card: #111827;
            --card-border: #243041;
            --text: #e5edf7;
            --muted: #9aa8bc;
            --accent: #60a5fa;
            --accent-soft: #1e3a5f;

            --major-bg: #3b1114;
            --major-text: #fca5a5;

            --moderate-bg: #3a2a10;
            --moderate-text: #fcd34d;

            --minor-bg: #172554;
            --minor-text: #93c5fd;

            --ok-bg: #052e16;
            --ok-text: #86efac;

            --unknown-bg: #1f2937;
            --unknown-text: #cbd5e1;

            --table-head: #172130;
            --shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
        }}
    }}

    * {{
        box-sizing: border-box;
    }}

    body {{
        font-family: Inter, Segoe UI, Arial, sans-serif;
        margin: 0;
        padding: 28px;
        background: var(--bg);
        color: var(--text);
    }}

    .wrapper {{
        max-width: 1280px;
        margin: 0 auto;
    }}

    h1 {{
        margin: 0 0 14px 0;
        font-size: 2.25rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }}

    h2 {{
        margin: 0 0 14px 0;
        font-size: 1.45rem;
        font-weight: 750;
    }}

    .badge {{
        display: inline-block;
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 18px;
    }}

    .sev-major {{ background: var(--major-bg); color: var(--major-text); }}
    .sev-moderate {{ background: var(--moderate-bg); color: var(--moderate-text); }}
    .sev-minor {{ background: var(--minor-bg); color: var(--minor-text); }}
    .sev-ok {{ background: var(--ok-bg); color: var(--ok-text); }}
    .sev-unknown {{ background: var(--unknown-bg); color: var(--unknown-text); }}

    .card {{
        background: var(--card);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 18px;
        box-shadow: var(--shadow);
    }}

    .grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 14px;
    }}

    .metric {{
        background: transparent;
        border: 1px solid var(--card-border);
        border-radius: 12px;
        padding: 14px 16px;
    }}

    .label {{
        font-size: 0.85rem;
        color: var(--muted);
        margin-bottom: 8px;
        font-weight: 600;
    }}

    .value {{
        font-size: 1.15rem;
        font-weight: 750;
        line-height: 1.2;
    }}

    .small {{
        color: var(--muted);
        font-size: 0.88rem;
        margin-top: 4px;
    }}

    .section-title {{
        border-left: 5px solid var(--accent);
        padding-left: 12px;
    }}

    .env-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px 24px;
    }}

    .env-item {{
        padding: 4px 0;
    }}

    .env-item b {{
        color: var(--text);
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        overflow: hidden;
        border-radius: 12px;
    }}

    th, td {{
        text-align: left;
        padding: 12px 14px;
        border-bottom: 1px solid var(--card-border);
    }}

    th {{
        background: var(--table-head);
        font-size: 0.92rem;
        font-weight: 700;
    }}

    td {{
        font-size: 0.97rem;
    }}

    tr:last-child td {{
        border-bottom: none;
    }}

    ul {{
        margin: 10px 0 0 18px;
        padding: 0;
    }}

    li {{
        margin-bottom: 6px;
    }}

    .kv {{
        margin: 10px 0;
        line-height: 1.6;
    }}

    .kv b {{
        color: var(--text);
    }}

    .footer-note {{
        color: var(--muted);
        font-size: 0.85rem;
    }}

    @media (max-width: 900px) {{
        .grid {{
            grid-template-columns: 1fr;
        }}

        .env-grid {{
            grid-template-columns: 1fr;
        }}

        body {{
            padding: 16px;
        }}
    }}
    </style>
    </head>
    <body>
    <div class="wrapper">

    <h1>Build Regression Report</h1>
    <div class="badge {sev_class}">{esc(sev)}</div>

    <div class="card">
    <div class="grid">
        <div class="metric">
        <div class="label">Baseline Build</div>
        <div class="value">{esc(format_time(result.get("baseline_total_ms", 0)))}</div>
        </div>
        <div class="metric">
        <div class="label">Candidate Build</div>
        <div class="value">{esc(format_time(result.get("candidate_total_ms", 0)))}</div>
        </div>
        <div class="metric">
        <div class="label">Total Change</div>
        <div class="value">{esc(format_time(abs(result.get("total_delta_ms", 0))))}</div>
        <div class="small">{esc(f"{result.get('percent_total', 0):+.1f}%")}</div>
        </div>
        <div class="metric">
        <div class="label">Build Type</div>
        <div class="value">{esc(classify_build_type(result.get("percent_total", 0)))}</div>
        </div>
        <div class="metric">
        <div class="label">Confidence</div>
        <div class="value">{esc(result.get("confidence", "Unknown"))}</div>
        </div>
        <div class="metric">
        <div class="label">Regression Gate</div>
        <div class="value">{esc(result.get("regression_gate_reason", "Unknown"))}</div>
        </div>
    </div>
    </div>

    <div class="card">
    <h2 class="section-title">Environment</h2>
    <div class="env-grid">
        <div class="env-item"><b>Baseline Backend:</b> {esc(result.get("baseline_backend", "Unknown"))}</div>
        <div class="env-item"><b>Candidate Backend:</b> {esc(result.get("candidate_backend", "Unknown"))}</div>
        <div class="env-item"><b>Baseline Platform:</b> {esc(result.get("baseline_platform", "Unknown"))}</div>
        <div class="env-item"><b>Candidate Platform:</b> {esc(result.get("candidate_platform", "Unknown"))}</div>
        <div class="env-item"><b>Baseline Size:</b> {esc(f"{result.get('baseline_size_mb', 0):.2f} MB")}</div>
        <div class="env-item"><b>Candidate Size:</b> {esc(f"{result.get('candidate_size_mb', 0):.2f} MB")}</div>
        <div class="env-item"><b>Size Change:</b> {esc(f"{result.get('size_delta_mb', 0):+.2f} MB")}</div>
        <div class="env-item"><b>Parse Quality:</b> {esc(result.get("parse_quality", "Unknown"))}</div>
    </div>
    </div>

    <div class="card">
    <h2 class="section-title">Top Contributors</h2>
    <table>
        <thead>
        <tr>
            <th>Step</th>
            <th>Baseline</th>
            <th>Candidate</th>
            <th>Delta</th>
            <th>Contribution</th>
        </tr>
        </thead>
        <tbody>
        {rows}
        </tbody>
    </table>
    </div>

    <div class="card">
    <h2 class="section-title">Diagnostic Analysis</h2>
    <div class="kv"><b>Root Classification:</b> {esc(diag.get("code", "N/A"))}</div>
    <div class="kv"><b>Primary Cause:</b> {esc(diag.get("cause", "N/A"))}</div>
    <div class="kv"><b>Likely Reason:</b> {esc(diag.get("likely_reason", "N/A"))}</div>
    <div class="kv"><b>Suggested Fix:</b> {esc(diag.get("suggested_fix", "N/A"))}</div>
    </div>

    <div class="card">
    <h2 class="section-title">Incident Response</h2>
    <div class="kv"><b>Owner To Ping:</b> {esc(diag.get("owner", "N/A"))}</div>
    <div class="kv"><b>Confidence Reason:</b> {esc(diag.get("confidence_why", "N/A"))}</div>
    <div class="kv"><b>Immediate Next Actions:</b></div>
    <ul>{next_actions}</ul>
    </div>

    <div class="card">
    <h2 class="section-title">Parse Diagnostics</h2>
    <ul>{warning_html}</ul>
    </div>

    </div>
    </body>
    </html>
    """


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
    parser.add_argument("--html", action="store_true",
                    help="Output HTML report")
    parser.add_argument("--html-out", default="build_report.html",
                    help="Path to save HTML report")
    parser.add_argument("--build-output", default=None,
                    help="Path to built player/output folder for size calculation")
    parser.add_argument("--platform", default=None,
                    help="Explicit platform override (e.g. StandaloneWindows64)")




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

    if args.build_output:
        cand["size_mb"] = get_build_size_mb(args.build_output)
    if args.platform:
        cand["platform"] = args.platform

    analysis = analyze_build(base, cand)

    # Output modes
    if args.json:
        print(json.dumps(analysis, indent=2))
    elif args.markdown:
        print(generate_markdown_report(analysis))
    elif args.html:
        html_report = generate_html_report(analysis)
        with open(args.html_out, "w", encoding="utf-8") as f:
            f.write(html_report)
        print(f"HTML report written to: {args.html_out}")
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
