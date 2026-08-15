#the actual background job: retry logic, failover decsionns, and all databases writes now will run in the worker instead of inside the request
from app.database import SessionLocal
from app.models import Payment, AuditLog, GatewayAttempt
from app.gateways.gateway_a import GatewayA
from app.gateways.gateway_b import GatewayB
from app.retry import call_with_retries
from app.queue_config import task_queue

MAX_RETRY_ROUNDS = 3


def process_payment(payment_id: int):
    db = SessionLocal()
    payment = db.query(Payment).filter_by(id=payment_id).first()

    if payment is None:
        db.close()
        return

    gateway_a = GatewayA()
    attempts_a, result_a = call_with_retries(gateway_a, payment.amount, payment.currency, max_attempts=2)

    for i, attempt in enumerate(attempts_a, start=1):
        db.add(GatewayAttempt(
            payment_id=payment.id,
            gateway_name="gateway_a",
            attempt_number=i,
            status=attempt["status"],
            transaction_id=attempt.get("transaction_id"),
            response_data=str(attempt),
        ))
    db.commit()

    if result_a["status"] == "success":
        final_result = result_a
        gateway_used = "gateway_a"
    else:
        gateway_b = GatewayB()
        attempts_b, result_b = call_with_retries(gateway_b, payment.amount, payment.currency, max_attempts=2)

        for i, attempt in enumerate(attempts_b, start=1):
            db.add(GatewayAttempt(
                payment_id=payment.id,
                gateway_name="gateway_b",
                attempt_number=i,
                status=attempt["status"],
                transaction_id=attempt.get("transaction_id"),
                response_data=str(attempt),
            ))
        db.commit()

        final_result = result_b
        gateway_used = "gateway_b"

    old_status = payment.status

    if final_result["status"] == "success":
        payment.status = "succeeded"
        payment.gateway_used = gateway_used
        db.add(AuditLog(payment_id=payment.id, old_status=old_status, new_status=payment.status))
        db.commit()
        db.close()
        return

    # Both gateways failed this round.
    payment.retry_count += 1

    if payment.retry_count >= MAX_RETRY_ROUNDS:
        payment.status = "dead_letter"
        db.add(AuditLog(
            payment_id=payment.id,
            old_status=old_status,
            new_status="dead_letter",
            note=f"Gave up after {payment.retry_count} full rounds through both gateways.",
        ))
        db.commit()
        db.close()
        return

    payment.status = "failed"
    db.add(AuditLog(payment_id=payment.id, old_status=old_status, new_status="failed"))
    db.commit()
    db.close()

    task_queue.enqueue(process_payment, payment.id)  # requeue for another full round