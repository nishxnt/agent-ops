.PHONY: install format test lint smoke-infra run-mock run-local deploy teardown

install:
	uv sync

format:
	uv run black .
	uv run ruff check --fix .

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run black --check .
	uv run mypy

smoke-infra:
	AGENTOPS_MODE=mock uv run python -m agentops.dev.run_mock_pipeline

run-mock:
	AGENTOPS_MODE=mock uv run agentops-run "What is FAISS?"

run-local:
	AGENTOPS_MODE=local uv run agentops-run "What is FAISS?"

deploy:
	@echo "Kubernetes deployment is introduced after Phase 0."

teardown:
	@echo "Kubernetes teardown is introduced after Phase 0."
