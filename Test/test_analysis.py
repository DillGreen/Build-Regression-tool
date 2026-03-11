from builddiff_advanced import parse_log, analyze_build

def test_analyze_build_returns_result():
    base = parse_log("tests/sample_logs/baseline_log.txt")
    cand = parse_log("tests/sample_logs/candidate_log.txt")

    result = analyze_build(base, cand)

    assert isinstance(result, dict)
    assert "severity" in result
    assert "contributors" in result
    assert "diagnosis" in result
