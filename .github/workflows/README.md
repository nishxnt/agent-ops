# CI/CD Workflows

- **ci.yml** - lint + test on every push and PR. Excludes deployment-tooling tests (`docker`, `k8s`, `helm` markers) which run in dedicated workflows below.
- (M2 will add: **docker-smoke.yml**)
- (M3 will add: **k8s-smoke.yml**)

Branch strategy: every push triggers CI on the pushed branch. PRs to `dev` or `main` additionally trigger CI on the merge candidate.
