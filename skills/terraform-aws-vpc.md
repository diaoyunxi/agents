---
name: terraform-aws-vpc
description: Generate a Terraform-format AWS VPC template with public/private subnets, IGW, NAT gateway, route tables, and security groups. Use when the user asks for a VPC or networking Terraform.
when_to_use: 'generate a Terraform VPC', 'create an AWS VPC with public/private subnets', 'one-click VPC template'.
---

# Terraform AWS VPC

Generate a Terraform-format AWS VPC template with subnets, routing, and internet access.

## When to use
- "generate a Terraform VPC", "create an AWS VPC with public/private subnets", "one-click VPC template".

## What to produce
A set of `.tf` files that create:
1. **VPC** — with `enable_dns_support` and `enable_dns_hostnames` true; a `cidr` input.
2. **Subnets**
   - Public subnets (one per AZ requested) with `map_public_ip_on_launch`.
   - Private subnets (one per AZ) that route to a NAT Gateway.
   - Use `aws_efs`/`aws_subnet` with `for_each` over AZs for symmetry.
3. **Internet Gateway** + **public route table** with a default route (0.0.0.0/0 → IGW).
4. **NAT Gateway** (in a public subnet) + **private route table** with default route → NAT.
5. **Route table associations** (public subnets → public RT, private subnets → private RT).
6. **Security groups** (optional) — a default-deny group with explicit ingress/egress rules the user specifies.
7. **Outputs** — `vpc_id`, `public_subnet_ids`, `private_subnet_ids`, `igw_id`, `nat_gateway_id`.

## Best practices baked in
- Inputs: `aws_region` (provider), `vpc_cidr`, `public_subnet_cidrs`, `private_subnet_cidrs`, `aws_zones` (or auto-spawn all AZs).
- Tag all resources with a common `Name` tag set and `managed-by = "terraform"`.
- Use `for_each` keyed on AZ name for deterministic addressing.
- Keep NAT Gateway cost in mind; for dev, allow a `nat_gateway = true` toggle.

## Steps
1. Confirm region, CIDR, and how many AZs the user wants (or auto-detect via `data.aws_availability_zones`).
2. Write `main.tf`, `vpc.tf`, `subnets.tf`, `routing.tf`, `security.tf`, `variables.tf`, `outputs.tf`.
3. `terraform init && terraform validate` — must pass.
4. `terraform plan` to preview; confirm with the user before `apply`.

## Rules
- Never `terraform apply` without the user's explicit confirmation.
- Do not open 0.0.0.0/0 on management/DB ports; keep security groups least-privilege.
- Use current provider version; pin `required_providers` blocks.

## Stop conditions
- `terraform validate` and `plan` pass, outputs are complete, and the user has confirmed before any apply → stop.
