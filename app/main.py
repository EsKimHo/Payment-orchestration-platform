import json
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app.models import Payment, IdempotencyKey, AuditLog, GatewayAttempt, ProcessedWebhook
from app.queue_config import task_queue
from app.tasks import process_payment
from app.security import verify_signature
from app.admin import router as admin_router
app = FastAPI()
app.include_router(admin_router)


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

@app.post("/webhooks/gateway-callback")
async def gateway_webhook(request: Request, x_signature: str = Header(...)):
    raw_body = await request.body()

    if not verify_signature(raw_body, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(raw_body)
    event_id = payload["event_id"]
    transaction_id = payload["transaction_id"]
    new_status = payload["status"]

    db = SessionLocal()

    # Validate the transaction exists BEFORE marking this event as processed,
    # so a bad or unknown transaction doesn't permanently burn the event_id.
    attempt = db.query(GatewayAttempt).filter_by(transaction_id=transaction_id).first()
    if attempt is None:
        db.close()
        raise HTTPException(status_code=404, detail="Unknown transaction_id")

    try:
        db.add(ProcessedWebhook(event_id=event_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        return {"status": "already_processed"}

    payment = db.query(Payment).filter_by(id=attempt.payment_id).first()
    old_status = payment.status
    payment.status = new_status
    db.add(AuditLog(
        payment_id=payment.id,
        old_status=old_status,
        new_status=new_status,
        note="Updated via webhook",
    ))
    db.commit()
    payment_id = payment.id
    db.close()

    return {"status": "ok", "payment_id": payment_id, "new_status": new_status}