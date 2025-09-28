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
                "PK": PK(s),  # TENANT#t-037#USER#hot#S0
                "SK": SK(n, n),  # EVENT#0000000001#000001
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
        Limit=50,
    )["Items"]
    items.extend(shard_items)
    print(f"  Shard {s}: {len(shard_items)} items")

print(f"Total sharded events for {TENANT}: {len(items)}")
