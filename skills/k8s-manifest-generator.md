---
name: k8s-manifest-generator
description: Generate and validate production-grade Kubernetes YAML manifests (Deployment, Service, Ingress, HPA, ConfigMap/Secret) with probes, labels, and safety checks. Use when the user asks for k8s YAML or a Helm chart.
when_to_use: 'generate k8s manifests for this app', 'create a Deployment/Service/Ingress', 'fix these k8s YAMLs'.
---

# Kubernetes Manifest Generator

Generate and maintain production-grade Kubernetes manifests (YAML).

## When to use
- "generate k8s manifests for this app", "create a Deployment/Service/Ingress", "fix these k8s YAMLs".

## Steps
1. **Understand the workload**
   - Container image, port(s), env vars/secrets, replicas, resource needs, probes, and which namespace/labels.
   - Deployment vs other workloads (StatefulSet for DBs, Job/CronJob for batch, DaemonSet for node agents).
2. **Generate the objects**
   - **Deployment**: image with tag (never `:latest` in prod), `replicas`, selector/labels that match, `strategy` (RollingUpdate default; Recreate for single-instance), readiness/liveness probes, resource requests/limits.
   - **Service**: `ClusterIP` default; `NodePort`/`LoadBalancer` only when externally reachable.
   - **Ingress / Gateway**: host, TLS, and path rules; a secret for certs.
   - **ConfigMap / Secret**: reference by key; never put real secrets in a ConfigMap.
   - **HorizontalPodAutoscaler** (optional) when resource scaling is wanted.
   - **Namespace** and/or a **Helm chart** for complex apps.
3. **Naming & labels**
   - `app.kubernetes.io/name`, `instance`, `version`, `component` labels; keep `matchLabels` consistent with the Deployment's `labels`.
4. **Validate**
   - `kubectl apply --dry-run=client -f <file>` or `kubeval` / `kubectl apply --dry-run=server` for schema + policy checks.
   - Check `kubectl explain` for any unfamiliar field.
5. **Safety**
   - No `hostNetwork: true`, no `:latest`, no missing limits, no secrets in plain YAML.
   - Confirm with the user before applying to a live cluster.

## Rules
- Every object in the same logical unit shares consistent labels and a shared `app:` name.
- Probes are required for long-running containers; set realistic initialDelay and timeouts.

## Stop conditions
- Manifests pass dry-run validation, probes/labels/limits are set, and no live apply has happened without confirmation → stop.
