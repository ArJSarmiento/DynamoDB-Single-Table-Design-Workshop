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