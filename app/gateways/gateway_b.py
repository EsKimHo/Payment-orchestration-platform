import time
import random
import uuid
from app.gateways.base import PaymentGateway


class GatewayB(PaymentGateway):
    def charge(self, amount: int, currency: str) -> dict:
        time.sleep(random.uniform(1.0, 2.5))  # slower than Gateway A

        if random.random() < 0.1:  # more reliable than Gateway A
            return {"status": "failure", "transaction_id": None}

        return {"status": "success", "transaction_id": str(uuid.uuid4())}

    def get_status(self, transaction_id: str) -> dict:
        return {"status": "success", "transaction_id": transaction_id}