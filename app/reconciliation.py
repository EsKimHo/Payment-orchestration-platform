from app.database import SessionLocal
from app.models import Payment, GatewayAttempt, AuditLog


def reconcile_payments():
    """
    Looks for payments stuck in 'pending' or 'failed' where the gateway
    actually recorded a success, meaning some update along the way
    (a webhook, a crashed worker, whatever) got lost. Fixes them.
    """
    db = SessionLocal()

    stuck_payments = db.query(Payment).filter(Payment.status.in_(["pending", "failed"])).all()
    corrected_count = 0

    for payment in stuck_payments:
        latest_attempt = (
            db.query(GatewayAttempt)
            .filter_by(payment_id=payment.id)
            .order_by(GatewayAttempt.created_at.desc())
            .first()
        )

        if latest_attempt and latest_attempt.status == "success" and payment.status != "succeeded":
            old_status = payment.status
            payment.status = "succeeded"
            payment.gateway_used = latest_attempt.gateway_name
            db.add(AuditLog(
                payment_id=payment.id,
                old_status=old_status,
                new_status="succeeded",
                note="Corrected by reconciliation job: gateway recorded success but payment record did not reflect it.",
            ))
            corrected_count += 1

    db.commit()
    db.close()
    print(f"Reconciliation run complete. Corrected {corrected_count} payment(s).")
    return corrected_count