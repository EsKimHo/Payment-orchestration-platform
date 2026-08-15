from datetime import datetime, timezone
from rq_scheduler import Scheduler
from app.queue_config import redis_conn
from app.reconciliation import reconcile_payments

scheduler = Scheduler(queue_name="default", connection=redis_conn)

for job in scheduler.get_jobs():
    if job.func_name == "app.reconciliation.reconcile_payments":
        scheduler.cancel(job)
        #to remove any previously scheduled copies of this job

scheduler.schedule(
    scheduled_time=datetime.now(timezone.utc),
    func=reconcile_payments,
    interval=60,  
    repeat=None,   # repeat forever
)

print("Reconciliation job scheduled to run every 60 seconds.")