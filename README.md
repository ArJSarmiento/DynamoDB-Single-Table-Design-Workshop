# Multi‑Tenant DynamoDB Workshop Guide

## Overview

In two hours, we’ll design and build **single‑table** and **multi‑tenant** data models on Amazon DynamoDB. You’ll learn how we navigate the lack of joins in DynamoDB, how to model access patterns, how **hot partitions** happen (and how to mitigate them), and two isolation approaches:

* A **shared multitenant table** (key prefixes + ABAC) to demonstrate tenant isolation within one table.
* A **personal table per attendee** for safe experiments and side‑by‑side comparison.

We’ll use **GitHub Codespaces**—a browser‑based VS Code—so there’s **no local setup**. All AWS access is done via **IAM Identity Center (SSO)** inside Codespaces.

---

## Agenda

1. DynamoDB fundamentals & the “no joins” mindset
2. Single‑table design (PK/SK, GSIs, sparse indexes)
3. Hot partitions & write‑sharding strategies
4. Multitenancy patterns (shared table with prefixes & ABAC)
5. Personal table design & GSI experiments
6. Observability (CloudWatch metrics & signals)
7. Cleanup & cost hygiene

---

## Roles in this guide

* **Organizers**: prepare AWS accounts, SSO, permissions, and repo scaffolding
* **Attendees**: follow the Codespaces + SSO setup and run labs

> If you’re an attendee, jump to **Attendee Setup**.

---

## Attendee Setup (Codespaces + AWS SSO)

### 0) Requirements

* GitHub account with access to the workshop repository
* **SSO voucher** (Start URL, SSO region, AWS account, role, and your Attendee ID)

### 1) Open the repo in Codespaces

1. Go to the workshop repository on GitHub.
2. Click **Code → Codespaces → Create codespace on main**.

### 2) Configure AWS CLI for SSO (inside Codespaces)

Open the terminal and run:

```bash
aws configure sso --profile dynamodb-workshop
```

When prompted, enter values from your voucher:

* **SSO Start URL**
* **SSO Region** (e.g., `ap-southeast-1`)
* **Account** (select the workshop account)
* **Role** (e.g., `WorkshopStudent`)
* **Profile name**: `workshop` (recommended)

Then sign in:

```bash
aws sso login --profile dynamodb-workshop
```

Use that profile & region in this shell:

```bash
export AWS_PROFILE=dynamodb-workshop
export AWS_REGION=ap-southeast-1
```

Verify access:

```bash
aws sts get-caller-identity
```

You should see your account and the role ARN.

### 3) (Optional) Bootstrap your environment

If the facilitator provides scripts, run:

```bash
bash scripts/bootstrap.sh --id "<ATTENDEE_ID>"
```

This typically deploys your **personal table** (`ws-att-<id>`) and seeds your namespace in the shared table (`ATT#<id>#…`).

### 4) Install Python dependencies (uv)

If the repo uses `uv` for dependencies:

```bash
uv sync --all-extras --all-groups
```

### 5) Start the labs

Your facilitator will direct you to the command(s) for each section, for example:

```bash
python -m labs.no_joins_intro --id "$ATTENDEE_ID"
python -m labs.single_table_queries --id "$ATTENDEE_ID"
python -m labs.hot_partitions --id "$ATTENDEE_ID"
python -m labs.multitenancy_abac --id "$ATTENDEE_ID"
python -m labs.personal_table_gsis --id "$ATTENDEE_ID"
```

### 6) Cleanup (end of workshop)

If infra was created:

```bash
bash scripts/cleanup.sh --id "$ATTENDEE_ID"
```

This deletes your personal table and purges your keys from the shared table.

---

## Troubleshooting

* **SSO expired** → `aws sso login --profile workshop`
* **Wrong account/profile** → `export AWS_PROFILE=workshop`
* **Region errors** → `export AWS_REGION=ap-southeast-1`
* **Permissions error on table** → confirm your Attendee ID and that your table is named `ws-att-<id>` and tagged `Owner=<id>`.
