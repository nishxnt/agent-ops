# CI/CD Workflows

- **ci.yml** - lint + test on every push and PR. Excludes deployment-tooling tests (`docker`, `k8s`, `helm` markers) which run in dedicated workflows below.
- **docker-smoke.yml** - builds the Docker image and runs the container smoke tests. Triggers only on PR to `dev`/`main` and manual dispatch. Slower than ci.yml; not run on every push.
- **k8s-smoke.yml** - provisions minikube, builds `agentops-api:dev` inside the minikube Docker daemon, deploys the Helm chart, and runs one end-to-end mock pipeline query through the Service. Triggers only on PR to `dev`/`main` and manual dispatch.

Branch strategy: every push triggers CI on the pushed branch. PRs to `dev` or `main` additionally trigger CI on the merge candidate.
