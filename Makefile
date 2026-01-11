.PHONY: test test-unit test-integration test-watch test-coverage test-build clean help

help:
	@echo "Tangerina Testing Commands"
	@echo "=========================="
	@echo "make test              - Run all tests with coverage"
	@echo "make test-unit         - Run only unit tests (fast)"
	@echo "make test-integration  - Run only integration tests"
	@echo "make test-watch        - Run tests in watch mode (auto-rerun on changes)"
	@echo "make test-coverage     - Run tests and open HTML coverage report"
	@echo "make test-build        - Build test Docker image"
	@echo "make clean             - Remove test artifacts"

test:
	cd deploy && docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit tangerina-test

test-unit:
	cd deploy && docker-compose -f docker-compose.test.yml --profile unit up --build --abort-on-container-exit tangerina-test-unit

test-integration:
	cd deploy && docker-compose -f docker-compose.test.yml --profile integration up --build --abort-on-container-exit tangerina-test-integration

test-watch:
	cd deploy && docker-compose -f docker-compose.test.yml --profile watch up --build tangerina-test-watch

test-coverage: test
	@echo "Opening coverage report..."
	@if command -v xdg-open > /dev/null; then \
		xdg-open htmlcov/index.html; \
	elif command -v open > /dev/null; then \
		open htmlcov/index.html; \
	else \
		echo "Coverage report generated at htmlcov/index.html"; \
	fi

test-build:
	cd deploy && docker-compose -f docker-compose.test.yml build

clean:
	rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	cd deploy && docker-compose -f docker-compose.test.yml down -v
