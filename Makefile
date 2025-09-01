.PHONY: help install test coverage lint format clean docs

help:
	@echo "Available commands:"
	@echo "  make install    - Install package in development mode with all dependencies"
	@echo "  make test       - Run all tests"
	@echo "  make coverage   - Run tests with coverage report"
	@echo "  make lint       - Run linters (flake8, mypy)"
	@echo "  make format     - Format code with black"
	@echo "  make clean      - Remove build artifacts and cache"
	@echo "  make docs       - Build documentation"

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pip install -e .
	@echo "✓ Installation complete"

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit -v -m unit

test-integration:
	pytest tests/integration -v -m integration

coverage:
	pytest --cov=ctk --cov-report=html --cov-report=term-missing
	@echo "✓ Coverage report generated in htmlcov/"

lint:
	flake8 ctk tests --max-line-length=100 --ignore=E203,W503
	mypy ctk --ignore-missing-imports
	@echo "✓ Linting complete"

format:
	black ctk tests
	isort ctk tests
	@echo "✓ Code formatted"

clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Cleaned build artifacts"

docs:
	@echo "Documentation generation not yet configured"
	@echo "TODO: Add sphinx or mkdocs configuration"