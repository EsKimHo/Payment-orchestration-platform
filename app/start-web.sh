#!/bin/sh
set -e

python -m app.schedule_setup

rq worker --url "$REDIS_URL" default &

rqscheduler --url "$REDIS_URL" &

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"