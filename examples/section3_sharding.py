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
