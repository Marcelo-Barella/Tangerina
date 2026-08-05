.PHONY: test test-unit test-integration test-watch test-coverage test-build clean help whisper-e2e

help:
	@echo "Tangerina Testing Commands"
	@echo "=========================="
	@echo "make test              - Run all tests with coverage"
	@echo "make test-unit         - Run only unit tests (fast)"
	@echo "make test-integration  - Run only integration tests"
	@echo "make test-watch        - Run tests in watch mode (auto-rerun on changes)"
	@echo "make test-coverage     - Run tests and open HTML coverage report"
	@echo "make test-build        - Build test Docker image"
	@echo "make whisper-e2e       - Build tiny local Whisper, warm, prove golden, tear down"
	@echo "make clean             - Remove test artifacts"

test:
	cd deploy && docker-compose --profile test up --build --abort-on-container-exit tangerina-test

test-unit:
	cd deploy && docker-compose --profile test-unit up --build --abort-on-container-exit tangerina-test-unit

test-integration:
	cd deploy && docker-compose --profile test-integration up --build --abort-on-container-exit tangerina-test-integration

test-watch:
	cd deploy && docker-compose --profile test-watch up --build tangerina-test-watch

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
	cd deploy && docker-compose --profile test build

whisper-e2e:
	docker network inspect tangerina-network >/dev/null 2>&1 || docker network create tangerina-network
	cd deploy/whisper && docker compose -f docker-compose.yml -f docker-compose.model-test.yml up -d --build
	@echo "Waiting for /ready?warm=1 ..."
	@i=0; \
	until curl -fsS "http://127.0.0.1:5002/ready?warm=1" >/dev/null 2>&1; do \
		i=$$((i+1)); \
		if [ $$i -ge 90 ]; then \
			echo "whisper /ready did not become ready in time"; \
			cd deploy/whisper && docker compose -f docker-compose.yml -f docker-compose.model-test.yml logs --tail=80 || true; \
			cd deploy/whisper && docker compose -f docker-compose.yml -f docker-compose.model-test.yml down || true; \
			exit 1; \
		fi; \
		sleep 2; \
	done
	WHISPER_LIVE=1 WHISPER_API_URL=http://127.0.0.1:5002 .venv/bin/python -m pytest tests/whisper_live -m whisper_live -q; \
	status=$$?; \
	cd deploy/whisper && docker compose -f docker-compose.yml -f docker-compose.model-test.yml down || true; \
	exit $$status

clean:
	rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	cd deploy && docker-compose --profile test --profile test-unit --profile test-integration --profile test-watch down -v 2>/dev/null || true
