#the actual background job: retry logic, failover decsionns, and all databases writes now will run in the worker instead of inside the request
from app.database import SessionLocal
from app.models import Payment, AuditLog, GatewayAttempt
from app.gateways.gateway_a import GatewayA
from app.gateways.gateway_b import GatewayB
from app.retry import call_with_retries


def process_payment(payment_id: int):
    db = SessionLocal()
    payment = db.query(Payment).filter_by(id=payment_id).first()

    if payment is None:
        db.close()
        return

    # Try Gateway A first, with its own retry budget.
    gateway_a = GatewayA()
    attempts_a, result_a = call_with_retries(gateway_a, payment.amount, payment.currency, max_attempts=2)

    for i, attempt in enumerate(attempts_a, start=1):
        db.add(GatewayAttempt(
            payment_id=payment.id,
            gateway_name="gateway_a",
            attempt_number=i,
            status=attempt["status"],
            response_data=str(attempt),
        ))
    db.commit()

    if result_a["status"] == "success":
        final_result = result_a
        gateway_used = "gateway_a"
    else:
        # Gateway A's retry budget ran out — fail over to Gateway B.
        gateway_b = GatewayB()
        attempts_b, result_b = call_with_retries(gateway_b, payment.amount, payment.currency, max_attempts=2)

        for i, attempt in enumerate(attempts_b, start=1):
            db.add(GatewayAttempt(
                payment_id=payment.id,
                gateway_name="gateway_b",
                attempt_number=i,
                status=attempt["status"],
                response_data=str(attempt),
            ))
        db.commit()

        final_result = result_b
        gateway_used = "gateway_b"

    old_status = payment.status
    payment.status = "succeeded" if final_result["status"] == "success" else "failed"
    payment.gateway_used = gateway_used
    db.add(AuditLog(payment_id=payment.id, old_status=old_status, new_status=payment.status))
    db.commit()
    db.close()