#!/bin/bash
# Backend entrypoint script

set -e

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until pg_isready -h "${DATABASE_HOST}" -p "${DATABASE_PORT}" 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready"

# Wait for Redis
echo "Waiting for Redis..."
until redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping 2>/dev/null | grep -q PONG; do
  sleep 1
done
echo "Redis is ready"

# Wait for Kafka
echo "Waiting for Kafka..."
until nc -z "${KAFKA_HOST}" "${KAFKA_PORT}" 2>/dev/null; do
  sleep 1
done
echo "Kafka is ready"

# Run migrations
echo "Running database migrations..."
alembic upgrade head

echo "Starting ATLAS API server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
