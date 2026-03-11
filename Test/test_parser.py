from builddiff_advanced import parse_log

def test_parse_log_returns_dict():
    result = parse_log("tests/sample_logs/baseline_log.txt")
    assert isinstance(result, dict)

def test_parse_log_has_steps():
    result = parse_log("tests/sample_logs/baseline_log.txt")
    assert "steps" in result
    assert isinstance(result["steps"], dict)

def test_parse_log_has_build_time():
    result = parse_log("tests/sample_logs/baseline_log.txt")
    assert "player_build_ms" in result
