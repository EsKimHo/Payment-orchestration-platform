import os
from redis import Redis
from rq import Queue

redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
task_queue = Queue("default", connection=redis_conn)

# 0 for redis datavase 0 and port 6379 is default port and hostname is redis