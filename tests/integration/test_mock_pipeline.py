from agentops.dev.run_mock_pipeline import run_mock_pipeline


def test_mock_pipeline_completes_without_external_calls() -> None:
    result = run_mock_pipeline()

    assert result["status"] == "completed"
    assert result["mode"] == "mock"
