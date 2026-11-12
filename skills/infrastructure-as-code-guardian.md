---
name: infrastructure-as-code-guardian
description: Review, harden, and safely manage Infrastructure-as-Code (Terraform, Pulumi, CloudFormation, Ansible) with static scanning and a security checklist. Use when the user asks to audit or secure IaC.
when_to_use: 'review this Terraform', 'harden my IaC', 'audit our Pulumi/CloudFormation/Ansible', 'is this config secure'.
---

# Infrastructure-as-Code Guardian

Manage and secure IaC across tools (Terraform, Pulumi, CloudFormation, Ansible) with a security-first posture.

## When to use
- "review this Terraform", "harden my IaC", "audit our Pulumi/CloudFormation/Ansible", "is this config secure".

## Steps
1. **Identify the tool and scope** — Terraform, Pulumi, CloudFormation, or Ansible. Find the entry point (`main.tf`, `Pulumi.*.ts`/`go`/`python`, `*.yaml` template, `playbooks/*.yml`).
2. **Static security scan** — Run the matching policy engine:
   - Terraform: `checkov -f .` and/or `tfsec` / `tfk8s`, plus `terrascan`.
   - Pulumi: `pulumi scan`.
   - CloudFormation: `checkov` / `cfn-nag`.
   - Ansible: `ansible-lint` (style) + `checkov` (cloud resources in plays).
   - Collect findings; fix high/critical first.
3. **Security checklist** (tool-agnostic, apply to any of the four)
   - **No public exposure without need** — Security groups / NACLs / LB: default-deny; open only required ports to required CIDRs; never 0.0.0.0/0 on SSH/RDP/DB.
   - **Secrets** — No passwords/API keys in code; use the provider's secret manager or KMS.
   - **Encryption** — Enable at-rest encryption on storage (EBS/S3/RDS) and in-transit (TLS).
   - **Logging/monitoring** — CloudTrail/audit logging enabled; flow logs where relevant.
   - **Principles** — Least-privilege IAM; tag/owner labels; immutable builds; no destructive `force` without review.
   - **State safety** — TF state locked + encrypted + remote (S3+DynamoDB); Pulumi backend secure.
4. **Apply & validate**
   - Terraform: `terraform init && terraform validate && terraform plan` before any apply.
   - Pulumi: `pulumi preview` and review the diff.
   - CloudFormation: `aws cloudformation validate-template` then a change-set preview.
   - Ansible: `ansible-playbook --check` (dry run) first.

## Rules
- Never run an apply/preview that makes a destructive or public-facing change without the user's explicit confirmation.
- Report every open high/critical finding; do not claim "secure" while any remains.

## Stop conditions
- The plan/preview shows only the intended resources, all high/critical findings are resolved, and a dry-run passes → stop.
