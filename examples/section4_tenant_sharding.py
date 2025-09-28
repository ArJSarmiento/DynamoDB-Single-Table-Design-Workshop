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
SHARDS = ["S0", "S1", "S2", "S3"]

tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
PK = lambda s: f"TENANT#{TENANT}#USER#hot#{s}"
SK = lambda t, n: f"EVENT#{t:010d}#{n:06d}"
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
items = []
for s in SHARDS:
    items += tbl.query(
        KeyConditionExpression=Key("PK").eq(PK(s)), ScanIndexForward=False, Limit=50
    )["Items"]
print("Sharded events for", TENANT, "->", len(items))
