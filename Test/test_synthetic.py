from builddiff_advanced import run_synthetic_test

def test_synthetic_runs():
    result = run_synthetic_test()
    assert isinstance(result, dict)
    assert "severity" in result
    assert "diagnosis" in result
    assert "contributors" in result
