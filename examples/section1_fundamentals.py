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
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": PROFILE_SK("u123"), "type": "USER", "name": "Ada"})
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": ORDER_SK("20250927", "o1"), "type": "ORDER", "status": "PENDING"})
    bw.put_item(Item={"PK": USER_PK("u123"), "SK": ORDER_SK("20250928", "o2"), "type": "ORDER", "status": "SHIPPED"})

# Efficient: Query one partition
resp = tbl.query(KeyConditionExpression=Key("PK").eq(USER_PK("u123")))
print("Query (profile + orders):", resp["Items"])

# Inefficient: Scan the whole table (avoid in real apps)
print("Scan sample:", tbl.scan(Limit=5)["Items"])