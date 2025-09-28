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
PK = lambda uid: f"TENANT#{TENANT}#USER#{uid}"
SKP = lambda uid: f"PROFILE#{uid}"
SKO = lambda d, oid: f"ORDER#{d}#{oid}"

with tbl.batch_writer() as bw:
    bw.put_item(
        Item={
            "PK": PK("u1"),
            "SK": SKP("u1"),
            "type": "USER",
            "email": "u1@example.org",
        }
    )
    bw.put_item(
        Item={
            "PK": PK("u1"),
            "SK": SKO("20250928", "o1"),
            "type": "ORDER",
            "status": "PENDING",
            "GSI1PK": f"TENANT#{TENANT}#STATUS#PENDING",
            "GSI1SK": "20250928#o1",
        }
    )
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
print(tbl.query(KeyConditionExpression=Key("PK").eq(PK("u1")))["Items"])
