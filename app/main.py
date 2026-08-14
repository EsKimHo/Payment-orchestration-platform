from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Payment, IdempotencyKey, AuditLog
from app.queue_config import task_queue
from app.tasks import process_payment

app = FastAPI()


class PaymentRequest(BaseModel):
    idempotency_key: str
    amount: int
    currency: str


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Payment platform skeleton is alive"}


@app.post("/payments")
def create_payment(req: PaymentRequest):
    db = SessionLocal()

    try:
        idem = IdempotencyKey(key=req.idempotency_key, payment_id=None)
        db.add(idem)
        db.commit()
    except IntegrityError:
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

    # Hand off to the worker instead of calling the gateway here directly.
    task_queue.enqueue(process_payment, payment.id)

    response = {
        "id": payment.id,
        "status": payment.status,  # still "pending" at this point
        "amount": payment.amount,
        "currency": payment.currency,
    }
    db.close()
    return response