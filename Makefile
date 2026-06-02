.PHONY: install format test lint smoke-infra run-mock run-local serve docker-build docker-run docker-smoke k8s-up k8s-smoke k8s-down deploy teardown

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

serve:
	AGENTOPS_MODE=mock uv run agentops-api

docker-build:
	docker build -f docker/api.Dockerfile -t agentops-api:dev .

docker-run:
	docker run --rm -p 8000:8000 \
		-e AGENTOPS_MODE=mock \
		-e BUDGET_TOKEN_LIMIT=100000 \
		--name agentops-api-dev \
		agentops-api:dev

docker-smoke:
	@echo "Building image..."
	@docker build -q -f docker/api.Dockerfile -t agentops-api:smoke . >/dev/null
	@echo "Starting container..."
	@docker run --rm -d -p 8001:8000 \
		-e AGENTOPS_MODE=mock -e BUDGET_TOKEN_LIMIT=100000 \
		--name agentops-api-smoke agentops-api:smoke
	@echo "Waiting for ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		curl -fsS http://localhost:8001/healthz >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	@echo "Healthz:"; curl -s http://localhost:8001/healthz; echo
	@echo "Readyz:"; curl -s http://localhost:8001/readyz; echo
	@echo "POST /run:"; \
		run_id=$$(curl -s -X POST http://localhost:8001/run \
			-H 'content-type: application/json' \
			-d '{"query":"What is FAISS?"}' | python -c "import sys,json;print(json.load(sys.stdin)['run_id'])"); \
		echo "  run_id=$$run_id"; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			status=$$(curl -s http://localhost:8001/status/$$run_id | python -c "import sys,json;print(json.load(sys.stdin)['status'])"); \
			echo "  status=$$status"; \
			[ "$$status" = "COMPLETED" ] && break; \
			[ "$$status" = "FAILED" ] && break; \
			sleep 2; \
		done; \
		echo "Final status:"; curl -s http://localhost:8001/status/$$run_id | python -m json.tool
	@docker stop agentops-api-smoke >/dev/null
	@echo "Smoke complete."

k8s-up:
	minikube status > /dev/null 2>&1 || minikube start --cpus=2 --memory=4g
	eval $$(minikube docker-env) && \
		docker build -f docker/api.Dockerfile -t agentops-api:dev .
	kubectl apply -k k8s/
	kubectl rollout status deployment/agentops-api-gateway --timeout=120s
	@echo ""
	@echo "Service URL: $$(minikube service agentops-api-gateway --url)"

k8s-smoke:
	@url=$$(minikube service agentops-api-gateway --url); \
	echo "Healthz:"; curl -s $$url/healthz; echo; \
	echo "Readyz:"; curl -s $$url/readyz; echo; \
	echo "POST /run:"; \
	run_id=$$(curl -s -X POST $$url/run \
		-H 'content-type: application/json' \
		-d '{"query":"What is FAISS?"}' \
		| python -c "import sys,json;print(json.load(sys.stdin)['run_id'])"); \
	echo "  run_id=$$run_id"; \
	for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		status=$$(curl -s $$url/status/$$run_id \
			| python -c "import sys,json;print(json.load(sys.stdin)['status'])"); \
		echo "  status=$$status"; \
		[ "$$status" = "COMPLETED" ] && break; \
		[ "$$status" = "FAILED" ] && break; \
		sleep 2; \
	done; \
	echo "Final status:"; curl -s $$url/status/$$run_id | python -m json.tool

k8s-down:
	kubectl delete -k k8s/ || true

deploy:
	@echo "Kubernetes deployment is introduced after Phase 0."

teardown:
	@echo "Kubernetes teardown is introduced after Phase 0."
