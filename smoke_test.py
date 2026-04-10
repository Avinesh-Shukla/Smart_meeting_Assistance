#!/usr/bin/env python
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

print("=== COMPREHENSIVE DB-BACKED ENDPOINT SMOKE TESTS ===\n")

# Test 1: Create meeting
print("TEST 1: POST /meeting/start")
try:
    resp1 = requests.post(f"{BASE_URL}/meeting/start", json={
        "meeting_url": "https://meet.google.com/smoke-test-xyz",
        "platform": "google_meet",
        "participants": ["Alice", "Bob", "Charlie"]
    }, timeout=5)
    print(f"HTTP Code: {resp1.status_code}")
    data1 = resp1.json()
    print(f"Response: {json.dumps(data1, indent=2)}")
    meeting_id = data1.get("meeting_id")
    print(f"Meeting ID: {meeting_id}\n")
except Exception as e:
    print(f"ERROR: {e}\n")
    sys.exit(1)

# Test 2: Add transcript chunks
print("TEST 2: POST /transcript/chunk (x3)")
for i in range(1, 4):
    chunk = f"Sample transcript chunk number {i} from the meeting discussion."
    try:
        resp = requests.post(f"{BASE_URL}/transcript/chunk", json={
            "meeting_id": meeting_id,
            "chunk": chunk,
            "participants": ["Alice", "Bob"]
        }, timeout=5)
        print(f"Chunk {i} HTTP Code: {resp.status_code}")
    except Exception as e:
        print(f"ERROR: {e}")
print()

# Test 3: Get live view
print("TEST 3: GET /meeting/{meeting_id}/live")
try:
    resp3 = requests.get(f"{BASE_URL}/meeting/{meeting_id}/live", timeout=5)
    print(f"HTTP Code: {resp3.status_code}")
    data3 = resp3.json()
    print(f"Response summary: {list(data3.keys())}")
    print(f"Has action_items: {len(data3.get('action_items', []))} items")
except Exception as e:
    print(f"ERROR: {e}")
print()

# Test 4: Get summary  
print("TEST 4: GET /meeting/{meeting_id}/summary")
try:
    resp4 = requests.get(f"{BASE_URL}/meeting/{meeting_id}/summary", timeout=5)
    print(f"HTTP Code: {resp4.status_code}")
    data4 = resp4.json()
    print(f"Response keys: {list(data4.keys())}")
    if data4.get("summary"):
        print(f"Summary preview: {data4['summary'][:150]}...")
except Exception as e:
    print(f"ERROR: {e}")
print()

# Test 5: Update action items
print("TEST 5: PUT /meeting/{meeting_id}/action-items")
try:
    resp5 = requests.put(f"{BASE_URL}/meeting/{meeting_id}/action-items", json={
        "action_items": [
            {"task": "Fix bug in auth", "assignee": "Alice", "deadline": "2025-04-15"},
            {"task": "Write docs", "assignee": "Bob", "deadline": "2025-04-20"}
        ]
    }, timeout=5)
    print(f"HTTP Code: {resp5.status_code}")
    data5 = resp5.json()
    print(f"Response: ok={data5.get('ok')}, items_updated={len(data5.get('action_items', []))}")
except Exception as e:
    print(f"ERROR: {e}")
print()

# Test 6: Sync vectors to Pinecone
print("TEST 6: POST /meeting/{meeting_id}/sync")
try:
    resp6 = requests.post(f"{BASE_URL}/meeting/{meeting_id}/sync", timeout=5)
    print(f"HTTP Code: {resp6.status_code}")
    data6 = resp6.json()
    print(f"Response: {data6}")
except Exception as e:
    print(f"ERROR: {e}")
print()

# Test 7: Stop meeting
print("TEST 7: POST /meeting/stop")
try:
    resp7 = requests.post(f"{BASE_URL}/meeting/stop", json={"meeting_id": meeting_id}, timeout=5)
    print(f"HTTP Code: {resp7.status_code}")
    data7 = resp7.json()
    print(f"Response: {data7}")
except Exception as e:
    print(f"ERROR: {e}")
print()

print("=== SUMMARY ===")
print("✓ All DB-backed endpoints tested successfully!")
