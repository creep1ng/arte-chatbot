# ARTE Chatbot Makefile
# All code-related commands run through Docker

.PHONY: help up down rebuild logs shell lint format typecheck test test-cov evaluate health clean

# ============================================
# Servicios
# ============================================

up:
	docker compose up -d

down:
	docker compose down

rebuild:
	docker compose up -d --build

logs:
	docker compose logs backend

shell:
	docker compose exec backend bash

# ============================================
# Calidad de Código
# ============================================

lint:
	docker compose exec backend ruff check backend/ rag/

format:
	docker compose exec backend ruff format backend/ rag/

typecheck:
	docker compose exec backend mypy backend/ rag/

# ============================================
# Tests
# ============================================

test:
	docker compose exec backend pytest

test-cov:
	docker compose exec backend pytest --cov=backend --cov=rag --cov-report=term-missing

# ============================================
# Evaluación
# ============================================

evaluate:
	docker compose exec backend python -m evaluation

# ============================================
# Salud
# ============================================

health:
	@curl -s http://localhost:8000/health

# ============================================
# Limpieza
# ============================================

clean:
	docker compose down -v --remove-orphans
