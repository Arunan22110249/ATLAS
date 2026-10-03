#!/bin/bash
# Worker entrypoint script

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

echo "Starting ATLAS worker (${WORKER_TYPE:-ingestion})..."
exec python -m backend.workers.ingestion_worker
