.PHONY: help install setup dev logs test lint type-check format clean up down migrate seed

help:
	@echo "ATLAS Development Commands"
	@echo "============================"
	@echo "make install        - Install dependencies"
	@echo "make setup          - Set up development environment"
	@echo "make dev            - Start development server (docker-compose)"
	@echo "make up             - Start docker-compose services"
	@echo "make down           - Stop docker-compose services"
	@echo "make logs           - View service logs"
	@echo "make migrate        - Run database migrations"
	@echo "make seed           - Seed database with sample data"
	@echo "make test           - Run tests"
	@echo "make test-cov       - Run tests with coverage"
	@echo "make lint           - Run linting (ruff)"
	@echo "make type-check     - Run type checking (mypy)"
	@echo "make format         - Format code (black, ruff)"
	@echo "make clean          - Clean up temporary files"
	@echo "make create-admin   - Create admin user"

install:
	pip install -r requirements.txt

setup:
	cp .env.example .env
	$(MAKE) install
	$(MAKE) migrate

dev: up migrate
	@echo "ATLAS is running!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"
	@echo "Frontend: http://localhost:5173"
	@echo "Grafana: http://localhost:3000"

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f api

logs-worker:
	docker-compose logs -f worker-ingestion

migrate:
	@echo "Running database migrations..."
	docker-compose exec -T postgres psql -U atlas -d atlas -c "SELECT version();" > /dev/null 2>&1 || sleep 5
	alembic upgrade head

seed:
	@echo "Seeding database..."
	python -m backend.scripts.seed_data

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=backend --cov-report=html

lint:
	ruff check backend tests
	pylint backend tests

type-check:
	mypy backend

format:
	black backend tests
	ruff check --fix backend tests

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

create-admin:
	@echo "Creating admin user..."
	python -m backend.scripts.create_admin

# Quick start
quick-start: setup dev

# Production build
build-docker:
	docker build -f Dockerfile.backend -t atlas-api:latest .
	docker build -f Dockerfile.worker -t atlas-worker:latest .

# Terraform
tf-init:
	cd infrastructure/terraform && terraform init

tf-plan:
	cd infrastructure/terraform && terraform plan

tf-apply:
	cd infrastructure/terraform && terraform apply

tf-destroy:
	cd infrastructure/terraform && terraform destroy
