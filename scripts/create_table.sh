#!/usr/bin/env bash
set -euo pipefail

: "${ATTENDEE_ID:?Set ATTENDEE_ID, e.g. export ATTENDEE_ID=037}"
: "${AWS_REGION:?Set AWS_REGION, e.g. export AWS_REGION=ap-southeast-1}"
TABLE="ws-att-${ATTENDEE_ID}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Creating table ${TABLE} in ${AWS_REGION}..."
aws dynamodb create-table \
  --table-name "${TABLE}" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

aws dynamodb wait table-exists --table-name "${TABLE}"

ARN="arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${TABLE}"
aws dynamodb tag-resource --resource-arn "$ARN" --tags Key=Owner,Value="${ATTENDEE_ID}" || true

echo "Done. TABLE=${TABLE}"