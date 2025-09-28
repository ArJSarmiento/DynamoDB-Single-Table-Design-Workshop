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
