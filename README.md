# Multi‑Tenant DynamoDB Workshop Guide

## Overview

In two hours, we’ll design and build **single‑table** and **multi‑tenant** data models on Amazon DynamoDB. You’ll learn how we navigate the lack of joins in DynamoDB, how to model access patterns, how **hot partitions** happen (and how to mitigate them), and two isolation approaches:

* A **personal table per attendee** for safe experiments and side‑by‑side comparison (used in Sections 1–3 examples).
* A **shared multitenant table** (key prefixes + ABAC) introduced later in the workshop.

We’ll use **GitHub Codespaces**—a browser‑based VS Code—so there’s **no local setup**. All AWS access is done via **IAM Identity Center (SSO)** inside Codespaces.

---

## Agenda

1. DynamoDB fundamentals & the “no joins” mindset
2. Single‑table design (PK/SK, GSIs, sparse indexes)
3. Hot partitions & write‑sharding strategies
4. Multitenancy patterns (shared table with prefixes & ABAC)
5. Observability (CloudWatch metrics & signals)
6. Cleanup & cost hygiene

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
aws sso login --profile dynamodb-workshop
export AWS_PROFILE=dynamodb-workshop
export AWS_REGION=ap-southeast-1
```

Verify:

```bash
aws sts get-caller-identity
```

---

## Create your personal DynamoDB table (one‑time)

We’ll give each participant their **own** table named `ws-att-<ATTENDEE_ID>` so the early examples don’t depend on any shared table.

### Script: `scripts/create_table.sh`

Create this file and run it. It tags the table to you.

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${ATTENDEE_ID:?Set ATTENDEE_ID, e.g. export ATTENDEE_ID=037}"
: "${AWS_REGION:?Set AWS_REGION, e.g. export AWS_REGION=ap-southeast-1}"
TABLE="ws-att-${ATTENDEE_ID}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Creating table ${TABLE} in ${AWS_REGION}..."
aws dynamodb create-table \
  --table-name "${TABLE}" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

aws dynamodb wait table-exists --table-name "${TABLE}"

ARN="arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${TABLE}"
aws dynamodb tag-resource --resource-arn "$ARN" --tags Key=Owner,Value="${ATTENDEE_ID}" || true

echo "Done. TABLE=${TABLE}"
```

Run it:

```bash
chmod +x scripts/create_table.sh
export ATTENDEE_ID=<your-id>
./scripts/create_table.sh
export TABLE=ws-att-${ATTENDEE_ID}   # convenience env var for examples
```

### (Optional) Cleanup script: `scripts/delete_table.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${ATTENDEE_ID:?Set ATTENDEE_ID}"
: "${AWS_REGION:?Set AWS_REGION}"
TABLE="ws-att-${ATTENDEE_ID}"
echo "Deleting ${TABLE}..."
aws dynamodb delete-table --table-name "$TABLE"
aws dynamodb wait table-not-exists --table-name "$TABLE"
echo "Deleted."
```

---

## Section 1 — Lecture Notes: DynamoDB Fundamentals & the “No Joins” Mindset

**Goal:** Understand how DynamoDB stores and retrieves data so we can design access patterns without server‑side joins.

### What DynamoDB is (and isn’t)

* **Key‑Value + Document store** backed by **partitions**. You read efficiently by **Querying a partition key (PK)** and optionally filtering/sorting by **sort key (SK)**.
* There are **no server‑side joins**. We **shape the data** to match the app’s questions (access patterns) so a **single Query** returns what we need.

### Core terms

* **Item**: a JSON document.
* **PK / SK**: determine where items live and how they’re ordered.
* **Item Collection**: all items sharing the same PK (ideal read unit).
* **Query vs Scan**: `Query` hits one PK (fast/cheap); `Scan` walks the whole table (slow/expensive).
* **Capacity**: On‑Demand or Provisioned (RCU/WCU). Use CW metrics to watch **ThrottledRequests**.

### How to think without joins

* Put **things read together** under the **same PK** (user + their orders, ticket + its comments).
* Use **adjacency lists** to represent relationships (e.g., `USER#123` ↔ `ORDER#...`).
* If a required read can’t be served by the base PK/SK, add a **secondary access path** (GSI) or **write‑time fan‑out** (pre‑computed view).

> **Checkpoint:** You can explain why designing access patterns comes before table design.


### Example — Query vs Scan, item collections (uses your personal table)

**File:** `examples/section1_fundamentals.py`

```python
#!/usr/bin/env python3
import os, boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]  # export TABLE=ws-att-<id>

USER_PK = lambda u: f"USER#{u}"
PROFILE_SK = lambda u: f"PROFILE#{u}"
ORDER_SK = lambda ymd, oid: f"ORDER#{ymd}#{oid}"

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

# Seed related items under ONE PK
with tbl.batch_writer() as bw:
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": PROFILE_SK("u123"), "type": "USER", "name": "Ada"})
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": ORDER_SK("20250927", "o1"), "type": "ORDER", "status": "PENDING"})
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": ORDER_SK("20250928", "o2"), "type": "ORDER", "status": "SHIPPED"})

# Efficient: Query one partition
resp = tbl.query(KeyConditionExpression=Key("PK").eq(USER_PK("u123")))
print("Query (profile + orders):", resp["Items"])

# Inefficient: Scan the whole table (avoid in real apps)
print("Scan sample:", tbl.scan(Limit=5)["Items"])
```

Run:

```bash
export TABLE=ws-att-${ATTENDEE_ID}
python examples/section1_fundamentals.py
```

---

# Section 2 — Single‑Table Design (PK/SK, GSIs, Sparse Indexes)

**Goal:** Turn access patterns into a concrete single‑table model.

### Step 1: List access patterns

Example app questions:

1. Get a user profile and latest orders.
2. List all orders for a user by newest first.
3. Find orders by status across all users (e.g., “PENDING”).

### Step 2: Choose PK/SK to satisfy #1 and #2

* **PK:** `USER#<userId>` groups profile and orders together.
* **SK:** type‑prefixed and sortable:

  * `PROFILE#<userId>`
  * `ORDER#<yyyymmdd>#<orderId>` (newest last; reverse at read time or store negative timestamps)
* **Result:**

  * **Get profile + latest orders:** one `Query PK=USER#<id>` with `begins_with(SK, 'ORDER#')`.
  * **All orders for a user:** same Query, different limit/filter.

### Step 3: Add a GSI for cross‑user query (#3)

* **Need:** “Find orders by status across all users.”
* **GSI1 PK:** `STATUS#<status>`  **GSI1 SK:** `<yyyymmdd>#<orderId>`
* **Populate:** Write the order item with extra attributes projected to the GSI (or a small projection item).
* **Query:** `GSI1 PK=STATUS#PENDING` to list pending orders regardless of user.

### Sparse indexes (power move)

* Only some items carry the GSI keys → the index contains **only** relevant rows.
* Example: Only `ORDER` items have `status` attributes, so `GSI1` is naturally **sparse** and small.

### Practical conventions

* **Entity‑type prefixes** in keys: `USER#`, `ORDER#`, `TENANT#` keep patterns readable.
* **Composite SK**: `TYPE#timestamp#id` supports sorting and range filters.
* **Projection**: Use `KEYS_ONLY` or minimal attributes on GSIs unless the read needs more.

> **Checkpoint:** You can take three app questions and sketch PK/SK + a GSI that answer them without joins.


### Example A — Seed a single‑table layout (personal table)

**File:** `examples/section2_single_table_seed.py`

```python
#!/usr/bin/env python3
import os, boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]

PK_USER = lambda uid: f"USER#{uid}"
SK_PROFILE = lambda uid: f"PROFILE#{uid}"
SK_ORDER = lambda ts, oid: f"ORDER#{ts}#{oid}"

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

with tbl.batch_writer() as bw:
    bw.put_item(Item={"PK": PK_USER("u200"), "SK": SK_PROFILE("u200"), "type": "USER", "email": "ada@example.org"})
    bw.put_item(Item={"PK": PK_USER("u200"), "SK": SK_ORDER("20250925", "o100"), "type": "ORDER", "status": "PENDING"})
    bw.put_item(Item={"PK": PK_USER("u200"), "SK": SK_ORDER("20250926", "o101"), "type": "ORDER", "status": "PENDING"})
    bw.put_item(Item={"PK": PK_USER("u200"), "SK": SK_ORDER("20250928", "o102"), "type": "ORDER", "status": "SHIPPED"})

print("Seeded single-table items for user u200 in", TABLE)
```

### Example B — Sparse GSI for cross‑user status (personal table)

**File:** `examples/section2_gsi_sparse.py`

```python
#!/usr/bin/env python3
import os, time, boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]
GSI_NAME = "GSI1_Status"
client = boto3.client("dynamodb", region_name=REGION)

desc = client.describe_table(TableName=TABLE)["Table"]
idx = {i["IndexName"] for i in desc.get("GlobalSecondaryIndexes", []) or []}
if GSI_NAME not in idx:
    client.update_table(
        TableName=TABLE,
        AttributeDefinitions=[{"AttributeName": "GSI1PK", "AttributeType": "S"}, {"AttributeName": "GSI1SK", "AttributeType": "S"}],
        GlobalSecondaryIndexUpdates=[{"Create": {"IndexName": GSI_NAME, "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}, "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}}}]
    )
    while True:
        time.sleep(3)
        gsi = client.describe_table(TableName=TABLE)["Table"].get("GlobalSecondaryIndexes", [])
        if any(i["IndexStatus"] == "ACTIVE" and i["IndexName"] == GSI_NAME for i in gsi):
            break

r = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
r.put_item(Item={"PK": "USER#u200", "SK": "ORDER#20250928#o102", "type": "ORDER", "status": "SHIPPED", "GSI1PK": "STATUS#SHIPPED", "GSI1SK": "20250928#o102"})
r.put_item(Item={"PK": "USER#u200", "SK": "ORDER#20250926#o101", "type": "ORDER", "status": "PENDING", "GSI1PK": "STATUS#PENDING", "GSI1SK": "20250926#o101"})

print("PENDING orders across all users in personal table:")
print(r.query(IndexName=GSI_NAME, KeyConditionExpression=Key("GSI1PK").eq("STATUS#PENDING"))["Items"])
```

Run Section 2:

```bash
python examples/section2_single_table_seed.py
python examples/section2_gsi_sparse.py
```

---

# Section 3 — Hot Partitions & Write‑Sharding

**Goal:** Avoid throttling when traffic concentrates on a small keyspace.

### What is a hot partition?

* Too many requests targeting **one PK** (or a tiny set), exhausting that partition’s throughput even if table capacity overall looks fine.
* Symptoms: **ThrottledRequests** spikes, uneven **ConsumedWrite/ReadCapacityUnits**.

### Common causes

* Monotonic keys (e.g., `PK=ORDER#2025‑09‑28`, all writes land on “today”).
* Celebrity tenants/users, high‑fan‑in counters, or time‑series writes without bucketing.

### Mitigations

1. **Time bucketing**: Partition today’s writes across more buckets, e.g.,

   * `PK=ORDERS#2025‑09‑28#HOUR#13` or `...#MIN5#1535`
2. **Write sharding**: Add a small shard suffix chosen randomly or by load:

   * `PK=USER#<id>#S<0..3>`; clients spread writes across S0..S3;
   * Readers `Query` all shards (parallel or sequential) and merge results.
3. **Load‑aware keys**: Route heavy tenants/users to more shards dynamically (maintain a shard map in memory/Redis/DDB).
4. **GSIs to spread load**: Move a hot read pattern onto a differently keyed index.

### Read patterns with sharding

* Readers must **fan‑out** queries: request `S0..S3` in parallel (async), merge and sort in the app.
* Prefer **few shards** (e.g., 4 or 8). Too many shards increase read cost and complexity.

### Safety rails

* Use **On‑Demand** while modeling; switch to Provisioned + Autoscaling only when stable.
* Watch **CloudWatch metrics** per table **and** per‑partition (via DDB Enhanced Observability) to confirm the fix.

> **Checkpoint:** Given a hot PK, you can propose a new key that spreads load without breaking the app’s reads.

**File:** `examples/section3_sharding.py`

```python
#!/usr/bin/env python3
import os, random, boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]
USER_ID = "hotuser"; SHARDS = ["S0","S1","S2","S3"]

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

PK = lambda s: f"USER#{USER_ID}#{s}"
SK = lambda ts,n: f"EVENT#{ts:010d}#{n:06d}"

# Write across shards
with tbl.batch_writer() as bw:
    for n in range(120):
        s = random.choice(SHARDS)
        bw.put_item(Item={"PK": PK(s), "SK": SK(n,n), "type": "EVENT", "payload": {"n": n, "shard": s}})

# Fan-out reads and merge
items = []
for s in SHARDS:
    resp = tbl.query(KeyConditionExpression=Key("PK").eq(PK(s)), ScanIndexForward=False, Limit=50)
    items.extend(resp["Items"])

print("Fetched", len(items), "events across shards; first 5:", sorted(items, key=lambda x: x["SK"], reverse=True)[:5])
```

Run Section 3:

```bash
python examples/section3_sharding.py
```
