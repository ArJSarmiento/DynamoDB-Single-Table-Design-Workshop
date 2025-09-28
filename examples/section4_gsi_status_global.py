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
print(
    tbl.query(
        IndexName=GSI, KeyConditionExpression=Key("GSI2PK").eq("STATUS#PENDING")
    )["Items"]
)
