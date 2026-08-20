rq worker --url "$REDIS_URL" default &
python -m app.run_scheduler &
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
