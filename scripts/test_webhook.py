import os
import json
import hmac   #hash_based message authenticationn code
import hashlib  #cryptographic hash functions like sha-256
import urllib.request
from dotenv import load_dotenv
from urllib.error import HTTPError
load_dotenv()  # reads .env and loads it into this script's environment

SECRET = os.getenv("WEBHOOK_SECRET")
TRANSACTION_ID = "b19b3216-621a-47fe-b3a1-e1841c304bf1"

payload = {
    "event_id": "evt-002",
    "transaction_id": TRANSACTION_ID,
    "status": "succeeded",
}
body = json.dumps(payload).encode()
signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

req = urllib.request.Request(
    "http://localhost:8000/webhooks/gateway-callback",
    data=body,
    headers={"Content-Type": "application/json", "x-signature": signature},
    method="POST",
)
try:
    with urllib.request.urlopen(req) as response:
        print(response.status, response.read().decode())
except HTTPError as e:
    print(e.code, e.read().decode())