from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app.models import Payment, IdempotencyKey, AuditLog
from app.gateways.gateway_a import GatewayA
app=FastAPI()
gateway=GatewayA()

class PaymentRequest(BaseModel):
    idempotency_key: str
    amount: int
    currency: str

@app.get("/")
def read_root():
    return {"status": "ok","message":"Payment platform skeleton is alive"}

@app.post("/payments")
def create_payment(req: PaymentRequest):
    db = SessionLocal()
    # Step 1: try to CLAIM this idempotency key. This is the one line
    # that provides the whole no-double-charge guarantee — the unique
    # constraint on `key` means only one request can win this insert.
    try:
        idem = IdempotencyKey(key=req.idempotency_key, payment_id=None)
        db.add(idem)
        db.commit()
    except IntegrityError:
        # Someone already claimed this key — fetch and return their result.
        db.rollback()
        existing = db.query(IdempotencyKey).filter_by(key=req.idempotency_key).first()
        existing_payment = db.query(Payment).filter_by(id=existing.payment_id).first()
        db.close()
        return {
            "id": existing_payment.id,
            "status": existing_payment.status,
            "amount": existing_payment.amount,
            "currency": existing_payment.currency,
        }

    # Step 2: we won the claim — now actually create the payment.
    payment = Payment(
        idempotency_key=req.idempotency_key,
        amount=req.amount,
        currency=req.currency,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    idem.payment_id = payment.id
    db.add(AuditLog(payment_id=payment.id, old_status=None, new_status="pending"))
    db.commit()

    # Step 3: call the gateway and record the outcome.
    result = gateway.charge(payment.amount, payment.currency)
    old_status = payment.status
    payment.status = "succeeded" if result["status"] == "success" else "failed"
    payment.gateway_used = "gateway_a"
    db.add(AuditLog(payment_id=payment.id, old_status=old_status, new_status=payment.status))
    db.commit()

    response = {
        "id": payment.id,
        "status": payment.status,
        "amount": payment.amount,
        "currency": payment.currency,
    }
    db.close()
    return response