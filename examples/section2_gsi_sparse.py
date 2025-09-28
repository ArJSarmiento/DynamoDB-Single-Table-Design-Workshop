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
        AttributeDefinitions=[{"AttributeName": "GSI1PK", "AttributeType": "S"}, {"AttributeName": "GSI1SK", "AttributeType": "S"}],
        GlobalSecondaryIndexUpdates=[{"Create": {"IndexName": GSI_NAME, "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}, "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}}}]
    )
    while True:
        time.sleep(3)
        gsi = client.describe_table(TableName=TABLE)["Table"].get("GlobalSecondaryIndexes", [])
        if any(i["IndexStatus"] == "ACTIVE" and i["IndexName"] == GSI_NAME for i in gsi):
            break

r = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
r.put_item(Item={"PK": "USER#u200", "SK": "ORDER#20250928#o102", "type": "ORDER", "status": "SHIPPED", "GSI1PK": "STATUS#SHIPPED", "GSI1SK": "20250928#o102"})
r.put_item(Item={"PK": "USER#u200", "SK": "ORDER#20250926#o101", "type": "ORDER", "status": "PENDING", "GSI1PK": "STATUS#PENDING", "GSI1SK": "20250926#o101"})

print("PENDING orders across all users in personal table:")
print(r.query(IndexName=GSI_NAME, KeyConditionExpression=Key("GSI1PK").eq("STATUS#PENDING"))["Items"])