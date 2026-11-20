---
name: ci-cd-pipeline-generator
description: Generate a production-grade CI/CD pipeline for GitHub Actions, GitLab CI, CircleCI, or Jenkins, with security and deployment gating. Use when the user asks to set up or improve a build/deploy pipeline.
when_to_use: 'set up a CI/CD pipeline', 'add a GitHub Actions / GitLab CI / CircleCI / Jenkins pipeline', 'automate build and deploy'.
---

# CI/CD Pipeline Generator

Generate a production-grade CI/CD pipeline for a target provider.

## When to use
- "set up a CI/CD pipeline", "add a GitHub Actions / GitLab CI / CircleCI / Jenkins pipeline", "automate build and deploy".

## Steps
1. **Understand the project**
   - Language/runtime, build command, test command, artifact type, target environments (dev/stage/prod), and existing secrets.
   - Deployment mechanism (container image, VM, serverless, k8s).
2. **Design the stages**
   - **Lint + Test** → **Build artifact** (image/binary) → **Security scan** (deps, image) → **Deploy** (by env, with gating) → **Notify**.
   - Use a single source of truth for stage definitions; reuse via matrices/anchors for multiple envs.
3. **Implement per provider**
   - **GitHub Actions**: `.github/workflows/*.yml`. Use reusable workflows or a composite action for the shared build. Pin action versions by SHA or tag. Add `permissions:` to least-privilege. Cache deps. Run tests on PR, build+push image on branch/tag. Deploy with environment protection rules.
   - **GitLab CI**: `.gitlab-ci.yml`. Use `stages`, `only/except`, `needs` for DAG ordering, and artifacts for passing build outputs. Pin `image` tags.
   - **CircleCI**: `.circleci/config.yml`. Define orbs/local commands; use job caching; gate deploys with context references.
   - **Jenkins**: `Jenkinsfile` (Declarative pipeline). Use agent, tools, options (timestamps, timeout, retry), and stages with parallelism.
4. **Security & robustness**
   - Least-privilege secrets and tokens; no secrets echoed to logs.
   - Fail the pipeline on a red stage; don't continue on failure.
   - Scan dependencies and images; fail on high/critical.
   - Tag/immutable image builds; verify signatures where applicable.
   - Set sensible timeouts; make the pipeline idempotent.
5. **Verify** — Lint the config (e.g., `actionlint`, `checkov`, provider CLI). Run a dry build. Confirm each stage gate works (a failing test stops the pipeline).

## Rules
- Never commit secrets; reference them from the provider's secret store.
- Deploy to prod must be gated (environment protection / approval), not automatic on every push.
- Keep the pipeline file readable; extract complex steps into reusable units.

## Stop conditions
- Config lints clean, all stages have clear gates, and a representative run reaches the expected stage → stop.
