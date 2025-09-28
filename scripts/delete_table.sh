#!/usr/bin/env bash
set -euo pipefail
: "${ATTENDEE_ID:?Set ATTENDEE_ID}"
: "${AWS_REGION:?Set AWS_REGION}"
TABLE="ws-att-${ATTENDEE_ID}"
echo "Deleting ${TABLE}..."
aws dynamodb delete-table --table-name "$TABLE"
aws dynamodb wait table-not-exists --table-name "$TABLE"
echo "Deleted."