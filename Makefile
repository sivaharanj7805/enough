.PHONY: install dev test lint format build migrate clean help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm ci

dev: ## Start development servers (requires docker-compose)
	docker-compose up

dev-backend: ## Start only the backend
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Start only the frontend
	cd frontend && npm run dev

test: ## Run all tests
	$(MAKE) test-backend
	$(MAKE) test-frontend

test-backend: ## Run backend tests with coverage
	cd backend && pytest tests/ -v --cov=app --cov-report=term-missing

test-frontend: ## Run frontend tests
	cd frontend && npm test -- --run

lint: ## Run all linters
	$(MAKE) lint-backend
	$(MAKE) lint-frontend

lint-backend: ## Lint Python code with ruff
	cd backend && ruff check app/

lint-frontend: ## Lint TypeScript/React with ESLint
	cd frontend && npm run lint

format: ## Format all code
	cd backend && ruff format app/
	cd frontend && npx prettier --write src/

build: ## Build production Docker images
	docker build -t enough-backend:latest ./backend
	docker build -t enough-frontend:latest ./frontend

migrate: ## Run database migrations
	cd backend && python migrate.py

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	cd frontend && rm -rf .next node_modules/.cache 2>/dev/null || true
