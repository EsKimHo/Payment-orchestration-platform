import time
import random
import uuid
from app.gateways.base import PaymentGateway

class GatewayA(PaymentGateway):
    def charge(self, amount: int, currency: str) -> dict:
        time.sleep(random.uniform(0.2, 1.5))  # simulate fake network latency

        if random.random() < 0.3:  # simulate a 30% failure rate
            return {"status": "failure", "transaction_id": None}

        return {"status": "success", "transaction_id": str(uuid.uuid4())}

    def get_status(self, transaction_id: str) -> dict:
        return {"status": "success", "transaction_id": transaction_id}