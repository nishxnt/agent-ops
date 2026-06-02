# Kubernetes Deployment Artifacts

Captured from one real minikube deployment via Helm at Phase 4 completion when local tooling is available. Demonstrates:

- All k8s primitives created via the Helm chart
- Pod reaching Ready (livenessProbe + readinessProbe passing)
- NodePort service routing `/run` requests to the orchestrator
- Audit DB persisting across Pod restarts (PVC working)

Regenerate with:

```bash
make helm-install
kubectl get all,pvc,configmap,secret -l app.kubernetes.io/name=agentops > examples/k8s/kubectl_get_all.txt
kubectl describe pod -l app.kubernetes.io/name=agentops > examples/k8s/kubectl_describe_pod.txt
helm template agentops ./charts/agentops -f charts/agentops/values.dev.yaml > examples/k8s/rendered_chart.yaml
make k8s-smoke > examples/k8s/smoke_output.txt
```
