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
5. Cleanup & cost hygiene

---

## Attendee Setup (Codespaces + AWS SSO)

### 0) Requirements

* GitHub account with access to the workshop repository
* **IAM User Voucher** (Console Account ID, Username and Password)
* Generate an access key and secret access key:
  * Go to the top-right account menu and then select "Security credentials"
  ![alt text](image.png)
  * Scroll down until you see the "Create Access Key" button. Select this button.  
  ![alt text](image-1.png)
  * Select "Command-line Interface", toggle the confirmation, and then hit next.
  ![alt text](image-2.png)
  * Select "Create access key"
  ![alt text](image-3.png)
  * Copy the Access Key and the Secret Access Key
  ![alt text](image-4.png)

### 1) Open the repo in Codespaces
> **Note:** If you need to restart your Codespaces environment, make sure your environment variables are saved in a `.env` file so you don’t lose them.  
>  
> You can set this up as follows:
> 1. Copy the provided example file:  
>    ```bash
>    cp .env.example .env
>    ```
> 2. As you create environment variables (from different sections of the setup), add them to the `.env` file.  
> 3. After restarting Codespaces, reload the variables with:  
>    ```bash
>    export $(cat .env | xargs)
>    ```


1. Go to the workshop repository on GitHub.
2. Click **Code → Codespaces → Create codespace on main**.
   <img width="1396" height="622" alt="image" src="https://github.com/user-attachments/assets/fa3c8cad-337e-4e03-8d3b-2ac1dbd7158d" />


### 2) Configure AWS CLI Profile (inside Codespaces)

Open the terminal and run:

```bash
aws configure --profile dynamodb-workshop
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

---
## Pre Requisite
* **Step 1:** `uv sync --all-groups --all-extras`
* **Step 2:** `source .venv/bin/activate`

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
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]  # export TABLE=ws-att-<id>

USER_PK = lambda u: f"USER#{u}"
PROFILE_SK = lambda u: f"PROFILE#{u}"
ORDER_SK = lambda ymd, oid: f"ORDER#{ymd}#{oid}"

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

# Seed related items under ONE PK
with tbl.batch_writer() as bw:
    bw.put_item(
        Item={
            "PK": USER_PK("u123"),
            "SK": PROFILE_SK("u123"),
            "type": "USER",
            "name": "Ada",
        }
    )
    bw.put_item(
        Item={
            "PK": USER_PK("u123"),
            "SK": ORDER_SK("20250927", "o1"),
            "type": "ORDER",
            "status": "PENDING",
        }
    )
    bw.put_item(
        Item={
            "PK": USER_PK("u123"),
            "SK": ORDER_SK("20250928", "o2"),
            "type": "ORDER",
            "status": "SHIPPED",
        }
    )

# Efficient: Query one partition
resp = tbl.query(KeyConditionExpression=Key("PK").eq(USER_PK("u123")))
print("Query (profile + orders):", resp["Items"])

# Inefficient: Scan the whole table (avoid in real apps)
print("Scan sample:", tbl.scan(Limit=5)["Items"])
```

Run:

```bash
export TABLE=ws-att-${ATTENDEE_ID}
uv run examples/section1_fundamentals.py
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
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]

PK_USER = lambda uid: f"USER#{uid}"
SK_PROFILE = lambda uid: f"PROFILE#{uid}"
SK_ORDER = lambda ts, oid: f"ORDER#{ts}#{oid}"

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

with tbl.batch_writer() as bw:
    bw.put_item(
        Item={
            "PK": PK_USER("u200"),
            "SK": SK_PROFILE("u200"),
            "type": "USER",
            "email": "ada@example.org",
        }
    )
    bw.put_item(
        Item={
            "PK": PK_USER("u200"),
            "SK": SK_ORDER("20250925", "o100"),
            "type": "ORDER",
            "status": "PENDING",
        }
    )
    bw.put_item(
        Item={
            "PK": PK_USER("u200"),
            "SK": SK_ORDER("20250926", "o101"),
            "type": "ORDER",
            "status": "PENDING",
        }
    )
    bw.put_item(
        Item={
            "PK": PK_USER("u200"),
            "SK": SK_ORDER("20250928", "o102"),
            "type": "ORDER",
            "status": "SHIPPED",
        }
    )

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
        AttributeDefinitions=[
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexUpdates=[
            {
                "Create": {
                    "IndexName": GSI_NAME,
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            }
        ],
    )
    while True:
        time.sleep(3)
        gsi = client.describe_table(TableName=TABLE)["Table"].get(
            "GlobalSecondaryIndexes", []
        )
        if any(
            i["IndexStatus"] == "ACTIVE" and i["IndexName"] == GSI_NAME for i in gsi
        ):
            break

r = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
r.put_item(
    Item={
        "PK": "USER#u200",
        "SK": "ORDER#20250928#o102",
        "type": "ORDER",
        "status": "SHIPPED",
        "GSI1PK": "STATUS#SHIPPED",
        "GSI1SK": "20250928#o102",
    }
)
r.put_item(
    Item={
        "PK": "USER#u200",
        "SK": "ORDER#20250926#o101",
        "type": "ORDER",
        "status": "PENDING",
        "GSI1PK": "STATUS#PENDING",
        "GSI1SK": "20250926#o101",
    }
)

print("PENDING orders across all users in personal table:")
print(
    r.query(
        IndexName=GSI_NAME, KeyConditionExpression=Key("GSI1PK").eq("STATUS#PENDING")
    )["Items"]
)
```

Run Section 2:

```bash
uv run examples/section2_single_table_seed.py
uv run examples/section2_gsi_sparse.py
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
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ["TABLE"]
USER_ID = "hotuser"
SHARDS = ["S0", "S1", "S2", "S3"]

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

PK = lambda s: f"USER#{USER_ID}#{s}"
SK = lambda ts, n: f"EVENT#{ts:010d}#{n:06d}"

# Write across shards
with tbl.batch_writer() as bw:
    for n in range(120):
        s = random.choice(SHARDS)
        bw.put_item(
            Item={
                "PK": PK(s),
                "SK": SK(n, n),
                "type": "EVENT",
                "payload": {"n": n, "shard": s},
            }
        )

# Fan-out reads and merge
items = []
for s in SHARDS:
    resp = tbl.query(
        KeyConditionExpression=Key("PK").eq(PK(s)), ScanIndexForward=False, Limit=50
    )
    items.extend(resp["Items"])

print(
    "Fetched",
    len(items),
    "events across shards; first 5:",
    sorted(items, key=lambda x: x["SK"], reverse=True)[:5],
)
```

Run Section 3:

```bash
uv run examples/section3_sharding.py
```

---
# Section 4 — Multi-tenancy on DynamoDB

## 4.0 What is Multi-tenancy?

Multi-tenancy means multiple customers (**tenants**) share the same app and often the same database. On DynamoDB we care about:

* **Isolation**: A tenant must not see another tenant's data.
* **Performance**: Load from one tenant should not throttle others.
* **Operations & cost**: Minimize tables and overhead while staying safe.

---

## 4.1 Deployment & Isolation Models

* **Table‑per‑tenant (silo)**: simplest isolation; expensive to operate at scale.
* **Shared table (pooled)**: one table, many tenants → lower cost/ops, but you must encode tenant identity **in the keys** and enforce **ABAC** (attribute‑based access control).
* **Hybrid**: large/"noisy" tenants use silo; small tenants share a pooled table.

---

## 4.2 ABAC with `dynamodb:LeadingKeys` (Core Security Concept)

**Policy idea:** Tag each principal `tenant=<id>` and restrict access so the **leading key** of every request begins with that tenant prefix:

```json
{
  "Condition": {
    "ForAllValues:StringLike": {
      "dynamodb:LeadingKeys": ["TENANT#${aws:PrincipalTag/tenant}#*"]
    }
  }
}
```

**How it works:**
- Every DynamoDB operation checks if the partition key starts with your tenant prefix
- If you're tagged as `tenant=t-037`, you can only access keys starting with `TENANT#t-037#`
- This prevents cross-tenant data access at the IAM policy level

To make this work, every base‑table **PK** and any **GSI PK** used by attendees must include `TENANT#<id>`.

---

## 4.3 Key Patterns for a Shared Table

We'll use these conventions to ensure tenant isolation:

* **Table:** `WorkshopShared`
* **Base Table PK:** `TENANT#<tid>#USER#<uid>` (groups user data by tenant)
* **Base Table SK:** `PROFILE#<uid>` or `ORDER#<yyyymmdd>#<orderId>` (sorts by entity type and date)
* **GSI1 (tenant‑scoped status):**
  * `GSI1PK = TENANT#<tid>#STATUS#<status>` (tenant-scoped status queries)
  * `GSI1SK = <yyyymmdd>#<orderId>` (chronological sorting)
* **GSI2 (admin-only global status):**
  * `GSI2PK = STATUS#<status>` (cross-tenant status queries)
  * `GSI2SK = <tid>#<yyyymmdd>#<orderId>` (tenant and date sorting)

**Key Design Principles:**
- **Tenant prefix first**: Ensures ABAC policies work correctly
- **Entity hierarchy**: USER → PROFILE/ORDER maintains relationships
- **Sparse GSIs**: Only items with status populate the status indexes
- **Sortable keys**: Date-based sorting for time-series queries

---

## 4.4 Code Example — Seed Your Tenant Namespace

**Purpose:** Create sample data in your tenant's isolated namespace to demonstrate the multi-tenant data model.

**File:** `examples/section4_intro_seed.py`

```python
#!/usr/bin/env python3
import os, boto3
from boto3.dynamodb.conditions import Key

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ.get("SHARED_TABLE", "WorkshopShared")
TENANT = os.environ.get("TENANT_ID", "t-037")

ddb = boto3.resource("dynamodb", region_name=REGION)
tbl = ddb.Table(TABLE)

# Key generation functions - notice the tenant prefix in every PK
PK = lambda uid: f"TENANT#{TENANT}#USER#{uid}"
SKP = lambda uid: f"PROFILE#{uid}"
SKO = lambda d, oid: f"ORDER#{d}#{oid}"

with tbl.batch_writer() as bw:
    # User profile item
    bw.put_item(
        Item={
            "PK": PK("u1"),              # TENANT#t-037#USER#u1
            "SK": SKP("u1"),             # PROFILE#u1
            "type": "USER",
            "email": "u1@example.org",
        }
    )
    # Order 1 - includes GSI1 attributes for status queries
    bw.put_item(
        Item={
            "PK": PK("u1"),              # Same PK groups user and orders
            "SK": SKO("20250928", "o1"), # ORDER#20250928#o1
            "type": "ORDER",
            "status": "PENDING",
            # GSI1 attributes for tenant-scoped status queries
            "GSI1PK": f"TENANT#{TENANT}#STATUS#PENDING",
            "GSI1SK": "20250928#o1",
        }
    )
    # Order 2 - different status
    bw.put_item(
        Item={
            "PK": PK("u1"),
            "SK": SKO("20250929", "o2"),
            "type": "ORDER", 
            "status": "SHIPPED",
            "GSI1PK": f"TENANT#{TENANT}#STATUS#SHIPPED",
            "GSI1SK": "20250929#o2",
        }
    )

print("Seeded namespace for", TENANT, "in", TABLE)
# Query all items for this user (profile + orders in one query)
print(tbl.query(KeyConditionExpression=Key("PK").eq(PK("u1")))["Items"])
```

**What this demonstrates:**
- **Tenant isolation by design**: Every PK starts with `TENANT#<id>#`
- **Item collection pattern**: User profile and orders share the same PK
- **GSI population**: Orders include GSI1 attributes for status-based queries
- **Efficient reads**: One query returns user + all their orders

**Run:**

```bash
export TENANT_ID=t-<your-id>
export SHARED_TABLE=WorkshopShared
uv run examples/section4_intro_seed.py
```

---

## 4.5 Code Example — Verify Isolation (Attempt Cross‑Tenant Access)

**Purpose:** Test that ABAC policies prevent accessing another tenant's data, demonstrating security isolation.

**File:** `examples/section4_cross_tenant_attempt.py`

```python
#!/usr/bin/env python3
import os, boto3
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ.get("SHARED_TABLE", "WorkshopShared")
OTHER_TENANT = os.environ.get("OTHER_TENANT_ID", "t-999")

tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
try:
    # Attempt to read another tenant's data
    # This should FAIL if ABAC policies are working correctly
    resp = tbl.get_item(
        Key={"PK": f"TENANT#{OTHER_TENANT}#USER#u1", "SK": "PROFILE#u1"}
    )
    print("🚨 SECURITY ISSUE - Unexpectedly succeeded:", resp.get("Item"))
    print("This means tenant isolation is NOT working!")
except ClientError as e:
    print("✅ Security working correctly!")
    print(
        "Expected AccessDenied ->",
        e.response["Error"]["Code"],
        e.response["Error"].get("Message"),
    )
```

**What this demonstrates:**
- **Security validation**: Attempts to access data outside your tenant namespace
- **ABAC in action**: IAM policy with `dynamodb:LeadingKeys` should block this request
- **Expected behavior**: Should fail with `AccessDeniedException` when policies are configured
- **Troubleshooting**: If this succeeds, your IAM role has too broad permissions

**Expected outcomes:**
- ✅ **With restricted role**: `AccessDeniedException` - tenant isolation working
- ❌ **With PowerUser/Admin role**: Success - bypasses tenant isolation

**Run:**

```bash
export OTHER_TENANT_ID=t-000
uv run examples/section4_cross_tenant_attempt.py
```

---

## 4.6 Code Example — Tenant‑Scoped Status Queries (Sparse GSI)

**Purpose:** Query orders by status within your tenant using GSI1, demonstrating how sparse indexes enable efficient cross-entity queries while maintaining tenant isolation.

**File:** `examples/section4_gsi_status_scoped.py`

```python
#!/usr/bin/env python3
import os, boto3
from boto3.dynamodb.conditions import Key

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ.get("SHARED_TABLE", "WorkshopShared")
GSI = os.environ.get("GSI_TENANT_STATUS", "GSI1")
TENANT = os.environ.get("TENANT_ID", "t-037")

tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

# Query GSI1 for all PENDING orders in this tenant
resp = tbl.query(
    IndexName=GSI,
    KeyConditionExpression=Key("GSI1PK").eq(f"TENANT#{TENANT}#STATUS#PENDING"),
)
print("Pending orders for", TENANT, "->", resp["Items"])
```

**What this demonstrates:**
- **Sparse GSI pattern**: Only ORDER items (not USER profiles) populate GSI1
- **Tenant-scoped queries**: GSI1PK includes tenant prefix, maintaining isolation
- **Status-based access pattern**: "Find all pending orders for my tenant"
- **Efficient cross-entity queries**: Query orders across all users in your tenant
- **ABAC compliance**: GSI1PK starts with `TENANT#<id>#`, so policies allow access

**GSI1 Structure:**
```
GSI1PK: TENANT#t-037#STATUS#PENDING    GSI1SK: 20250928#o1
GSI1PK: TENANT#t-037#STATUS#SHIPPED    GSI1SK: 20250929#o2
```

**Why this works:**
- **Tenant isolation**: Can only query your tenant's status data
- **Sparse index**: Only items with `GSI1PK` appear in the index (orders, not profiles)
- **Sortable results**: GSI1SK allows chronological ordering of orders

**Run:**

```bash
uv run examples/section4_gsi_status_scoped.py
```

---

## 4.7 Optional (Admins Only): Global Cross‑Tenant GSI

**Purpose:** Query orders by status across ALL tenants using GSI2, demonstrating admin-level visibility that bypasses tenant isolation for operational monitoring.

**⚠️ Security Note:** This GSI intentionally breaks tenant isolation for admin use cases. Regular tenant users should NOT have access to this index.

**File:** `examples/section4_gsi_status_global.py`

```python
#!/usr/bin/env python3
import os, boto3
from boto3.dynamodb.conditions import Key

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ.get("SHARED_TABLE", "WorkshopShared")
GSI = os.environ.get("GSI_GLOBAL_STATUS", "GSI2_StatusGlobal")

tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

# Admin query: Find ALL pending orders across ALL tenants
print("Global pending orders across all tenants:")
print(
    tbl.query(
        IndexName=GSI, KeyConditionExpression=Key("GSI2PK").eq("STATUS#PENDING")
    )["Items"]
)
```

**What this demonstrates:**
- **Cross-tenant visibility**: Admin can see orders from all tenants
- **Global operational queries**: "Show all pending orders in the system"
- **Different access pattern**: GSI2PK has NO tenant prefix (`STATUS#PENDING` vs `TENANT#<id>#STATUS#PENDING`)
- **Admin-only access**: Regular tenant users can't query this GSI due to ABAC policies

**GSI2 Structure (Admin View):**
```
GSI2PK: STATUS#PENDING    GSI2SK: t-037#20250928#o1
GSI2PK: STATUS#PENDING    GSI2SK: t-042#20250928#o5  
GSI2PK: STATUS#SHIPPED    GSI2SK: t-037#20250929#o2
```

**Security implications:**
- ✅ **Admin users**: Can query GSI2 for system-wide monitoring
- ❌ **Tenant users**: ABAC policies block access (GSI2PK doesn't start with their tenant prefix)
- 🔧 **Data population**: Items need both GSI1 (tenant-scoped) AND GSI2 (global) attributes

**Creating GSI2 (if needed):**
```bash
aws dynamodb update-table --table-name WorkshopShared \
  --attribute-definitions AttributeName=GSI2PK,AttributeType=S AttributeName=GSI2SK,AttributeType=S \
  --global-secondary-index-updates '[{
    "Create": {
      "IndexName": "GSI2_StatusGlobal",
      "KeySchema": [
        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
        {"AttributeName": "GSI2SK", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }
  }]'
```

**Run (admin role only):**

```bash
uv run examples/section4_gsi_status_global.py
```

---

## 4.8 Dealing with Noisy Neighbors (Sharding Heavy Tenants)

**Purpose:** Demonstrate how to shard high-volume tenants across multiple partition keys to prevent hot partitions while maintaining tenant isolation.

**Problem:** A "noisy neighbor" tenant generates so much traffic that they exhaust their partition's throughput, potentially affecting other tenants or causing throttling.

**Solution:** Shard the heavy tenant's data across multiple partition keys, then fan-out reads across all shards.

**File:** `examples/section4_tenant_sharding.py`

```python
#!/usr/bin/env python3
import os, random, boto3
from boto3.dynamodb.conditions import Key

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE = os.environ.get("SHARED_TABLE", "WorkshopShared")
TENANT = os.environ.get("TENANT_ID", "t-037")
SHARDS = ["S0", "S1", "S2", "S3"]  # 4 shards to distribute load

tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

# Sharded PK pattern: includes shard suffix
PK = lambda s: f"TENANT#{TENANT}#USER#hot#{s}"
SK = lambda t, n: f"EVENT#{t:010d}#{n:06d}"

# Write phase: Distribute writes across shards randomly
print(f"Writing 120 events across {len(SHARDS)} shards...")
with tbl.batch_writer() as bw:
    for n in range(120):
        s = random.choice(SHARDS)  # Random shard selection
        bw.put_item(
            Item={
                "PK": PK(s),               # TENANT#t-037#USER#hot#S0
                "SK": SK(n, n),            # EVENT#0000000001#000001
                "type": "EVENT",
                "payload": {"n": n, "shard": s},
            }
        )

# Read phase: Fan-out queries across all shards
print("Reading from all shards...")
items = []
for s in SHARDS:
    shard_items = tbl.query(
        KeyConditionExpression=Key("PK").eq(PK(s)), 
        ScanIndexForward=False,  # Newest first
        Limit=50
    )["Items"]
    items.extend(shard_items)
    print(f"  Shard {s}: {len(shard_items)} items")

print(f"Total sharded events for {TENANT}: {len(items)}")
```

**What this demonstrates:**
- **Hot partition mitigation**: Spreads load across 4 partition keys instead of 1
- **Tenant isolation maintained**: All shards still start with `TENANT#<id>#`
- **Write distribution**: Random shard selection spreads writes evenly
- **Fan-out reads**: Application queries all shards and merges results
- **Performance trade-off**: More read requests but better write throughput

**Sharding Strategy:**
```
Original:  TENANT#t-037#USER#hot
Sharded:   TENANT#t-037#USER#hot#S0
           TENANT#t-037#USER#hot#S1  
           TENANT#t-037#USER#hot#S2
           TENANT#t-037#USER#hot#S3
```

**When to use sharding:**
- ✅ High-volume tenants causing throttling
- ✅ Time-series data with predictable hot spots
- ✅ When you can accept increased read complexity
- ❌ Low-volume tenants (adds unnecessary complexity)
- ❌ When strong consistency across shards is required

**Best practices:**
- **Few shards**: 2-8 shards typically sufficient
- **Consistent hashing**: For predictable shard selection
- **Monitoring**: Watch per-partition metrics to validate effectiveness
- **Gradual rollout**: Test with one tenant before applying broadly

**Run:**

```bash
uv run examples/section4_tenant_sharding.py
```

---

## 4.9 Complete Workshop Flow (Shared Table)

**Run all Section 4 examples in order to see the complete multi-tenant pattern:**

```bash
# 1. Set up your tenant environment
export TENANT_ID=t-<your-id>           # Your unique tenant ID
export SHARED_TABLE=WorkshopShared     # Shared multi-tenant table

# 2. Seed your tenant's data namespace
echo "=== Seeding tenant data ==="
uv run examples/section4_intro_seed.py

# 3. Query your tenant's orders by status (tenant-scoped)
echo "=== Tenant-scoped status query ==="
uv run examples/section4_gsi_status_scoped.py

# 4. Test tenant isolation (should fail with proper ABAC)
echo "=== Testing cross-tenant access (should be blocked) ==="
export OTHER_TENANT_ID=t-000
uv run examples/section4_cross_tenant_attempt.py

# 5. Optional: Demonstrate tenant sharding for high-volume scenarios
echo "=== Optional: Tenant sharding demo ==="
uv run examples/section4_tenant_sharding.py

# 6. Admin-only: Global cross-tenant queries (requires admin role)
echo "=== Admin-only: Global status queries ==="
# uv run examples/section4_gsi_status_global.py
```

**Expected Results:**
1. **Seed**: Creates user profile + 2 orders in your tenant namespace
2. **Status query**: Returns pending orders for your tenant only
3. **Cross-tenant test**: 
   - ✅ **With ABAC**: `AccessDeniedException` (security working)
   - ❌ **With PowerUser**: Success (bypasses tenant isolation)
4. **Sharding**: Distributes 120 events across 4 shards, demonstrates fan-out reads
5. **Global query**: Shows orders from all tenants (admin view only)

**Troubleshooting:**
- **Cross-tenant access succeeds**: Your IAM role has too broad permissions
- **GSI2 not found**: Run the GSI creation command from section 4.7
- **Access denied on own data**: Check `TENANT_ID` matches your IAM principal tag


# Resource Cleanup
### Cleanup script for DynamoDB tables: `scripts/delete_table.sh`

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

**Run:**

```bash
scripts/delete_table.sh
```

### Stop and Delete Codespace
Click **Code → Codespaces → Click the three dots → Stop Codespace → Delete**.
<img width="1113" height="934" alt="image" src="https://github.com/user-attachments/assets/a5107dbc-6a50-469c-b4a4-a741f4827635" />

