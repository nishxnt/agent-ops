.PHONY: test lint run-mock run-local deploy teardown

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run black --check .
	uv run mypy

run-mock:
	AGENTOPS_MODE=mock uv run python -m agentops.dev.run_mock_pipeline

run-local:
	AGENTOPS_MODE=local uv run python -m agentops.dev.run_mock_pipeline

deploy:
	@echo "Kubernetes deployment is introduced after Phase 0."

teardown:
	@echo "Kubernetes teardown is introduced after Phase 0."
