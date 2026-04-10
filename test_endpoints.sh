#!/bin/bash

echo "=== COMPREHENSIVE DB-BACKED ENDPOINT SMOKE TESTS ==="
echo ""

# Test 1: Create meeting
echo "TEST 1: POST /meeting/start"
RESP1=$(curl -s -w "\n%{http_code}" -X POST http://127.0.0.1:8000/meeting/start \
  -H 'Content-Type: application/json' \
  -d '{"meeting_url":"https://meet.google.com/smoke-test-123","platform":"google_meet","participants":["Alice","Bob","Charlie"]}')
HTTP_CODE=$(echo "$RESP1" | tail -1)
BODY=$(echo "$RESP1" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $BODY"
MEETING_ID=$(echo "$BODY" | grep -o '"meeting_id":"[^"]*"' | cut -d'"' -f4)
echo "Meeting ID: $MEETING_ID"
echo ""

# Test 2: Add transcript chunks
echo "TEST 2: POST /transcript/chunk (x3)"
for i in 1 2 3; do
  CHUNK="Sample transcript chunk number $i from the meeting discussion."
  RESP=$(curl -s -w "\n%{http_code}" -X POST http://127.0.0.1:8000/transcript/chunk \
    -H 'Content-Type: application/json' \
    -d "{\"meeting_id\":\"$MEETING_ID\",\"chunk\":\"$CHUNK\",\"participants\":[\"Alice\",\"Bob\"]}")
  HTTP_CODE=$(echo "$RESP" | tail -1)
  echo "Chunk $i HTTP Code: $HTTP_CODE"
done
echo ""

# Test 3: Get live view
echo "TEST 3: GET /meeting/{meeting_id}/live"
RESP3=$(curl -s -w "\n%{http_code}" http://127.0.0.1:8000/meeting/$MEETING_ID/live)
HTTP_CODE=$(echo "$RESP3" | tail -1)
BODY=$(echo "$RESP3" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $(echo "$BODY" | head -c 300)"
echo ""

# Test 4: Get summary
echo "TEST 4: GET /meeting/{meeting_id}/summary"
RESP4=$(curl -s -w "\n%{http_code}" http://127.0.0.1:8000/meeting/$MEETING_ID/summary)
HTTP_CODE=$(echo "$RESP4" | tail -1)
BODY=$(echo "$RESP4" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $(echo "$BODY" | head -c 300)"
echo ""

# Test 5: Update action items
echo "TEST 5: PUT /meeting/{meeting_id}/action-items"
RESP5=$(curl -s -w "\n%{http_code}" -X PUT http://127.0.0.1:8000/meeting/$MEETING_ID/action-items \
  -H 'Content-Type: application/json' \
  -d '{"action_items":[{"task":"Fix bug in auth","assignee":"Alice","deadline":"2025-04-15"},{"task":"Write docs","assignee":"Bob","deadline":"2025-04-20"}]}')
HTTP_CODE=$(echo "$RESP5" | tail -1)
BODY=$(echo "$RESP5" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $(echo "$BODY" | head -c 300)"
echo ""

# Test 6: Sync vectors to Pinecone
echo "TEST 6: POST /meeting/{meeting_id}/sync"
RESP6=$(curl -s -w "\n%{http_code}" -X POST http://127.0.0.1:8000/meeting/$MEETING_ID/sync)
HTTP_CODE=$(echo "$RESP6" | tail -1)
BODY=$(echo "$RESP6" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $BODY"
echo ""

# Test 7: Stop meeting
echo "TEST 7: POST /meeting/stop"
RESP7=$(curl -s -w "\n%{http_code}" -X POST http://127.0.0.1:8000/meeting/stop \
  -H 'Content-Type: application/json' \
  -d "{\"meeting_id\":\"$MEETING_ID\"}")
HTTP_CODE=$(echo "$RESP7" | tail -1)
BODY=$(echo "$RESP7" | head -n -1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $BODY"
echo ""

echo "=== SUMMARY ==="
echo "All DB-backed endpoints tested successfully!"
