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
resp = tbl.query(
    IndexName=GSI,
    KeyConditionExpression=Key("GSI1PK").eq(f"TENANT#{TENANT}#STATUS#PENDING"),
)
print("Pending for", TENANT, "->", resp["Items"])
