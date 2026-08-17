from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import Payment, GatewayAttempt, AuditLog
from app.queue_config import task_queue
from app.tasks import process_payment

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request,"admin.html", {"request": request})


@router.get("/admin/api/payments")
def admin_payments_api():
    db = SessionLocal()
    payments = db.query(Payment).order_by(Payment.id.desc()).all()

    stats = {"total": 0, "pending": 0, "succeeded": 0, "failed": 0, "dead_letter": 0}
    result = []
    for p in payments:
        stats["total"] += 1
        stats[p.status] = stats.get(p.status, 0) + 1
        result.append({
            "id": p.id,
            "idempotency_key": p.idempotency_key,
            "amount": p.amount,
            "currency": p.currency,
            "status": p.status,
            "gateway_used": p.gateway_used,
            "retry_count": p.retry_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })

    db.close()
    return {"stats": stats, "payments": result}


@router.get("/admin/api/payments/{payment_id}")
def admin_payment_detail(payment_id: int):
    db = SessionLocal()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    if payment is None:
        db.close()
        raise HTTPException(status_code=404, detail="Payment not found")

    attempts = (
        db.query(GatewayAttempt)
        .filter_by(payment_id=payment_id)
        .order_by(GatewayAttempt.created_at.asc())
        .all()
    )
    logs = (
        db.query(AuditLog)
        .filter_by(payment_id=payment_id)
        .order_by(AuditLog.changed_at.asc())
        .all()
    )

    result = {
        "gateway_attempts": [
            {
                "gateway_name": a.gateway_name,
                "attempt_number": a.attempt_number,
                "status": a.status,
                "transaction_id": a.transaction_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attempts
        ],
        "audit_log": [
            {
                "old_status": l.old_status,
                "new_status": l.new_status,
                "note": l.note,
                "changed_at": l.changed_at.isoformat() if l.changed_at else None,
            }
            for l in logs
        ],
    }
    db.close()
    return result


@router.post("/admin/payments/{payment_id}/replay")
def replay_payment(payment_id: int):
    db = SessionLocal()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    if payment is None:
        db.close()
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status not in ("failed", "dead_letter"):
        db.close()
        raise HTTPException(status_code=400, detail="Only failed or dead_letter payments can be replayed")

    old_status = payment.status
    old_retry_count = payment.retry_count
    payment.retry_count = 0
    payment.status = "pending"
    db.add(AuditLog(
        payment_id=payment.id,
        old_status=old_status,
        new_status="pending",
        note=f"Manually replayed from admin panel (retry_count reset from {old_retry_count} to 0).",
    ))
    db.commit()
    db.close()

    task_queue.enqueue(process_payment, payment_id)
    return {"status": "replay_queued", "payment_id": payment_id}