import hmac
import hashlib
import os

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-secret-change-me")

def verify_signature(raw_body: bytes, received_signature: str) -> bool:
   
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode(), raw_body,hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, received_signature)

# we used hmac.compare_digest to prevent timing attacks rather than using a sinmple ==