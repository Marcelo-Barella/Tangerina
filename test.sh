#!/bin/bash

set -e

cd "$(dirname "$0")"

case "${1:-all}" in
    all)
        echo "Running all tests with coverage..."
        cd deploy && docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit tangerina-test
        ;;
    unit)
        echo "Running unit tests..."
        cd deploy && docker-compose -f docker-compose.test.yml --profile unit up --build --abort-on-container-exit tangerina-test-unit
        ;;
    integration)
        echo "Running integration tests..."
        cd deploy && docker-compose -f docker-compose.test.yml --profile integration up --build --abort-on-container-exit tangerina-test-integration
        ;;
    watch)
        echo "Running tests in watch mode (Ctrl+C to stop)..."
        cd deploy && docker-compose -f docker-compose.test.yml --profile watch up --build tangerina-test-watch
        ;;
    coverage)
        echo "Running tests and generating coverage report..."
        cd deploy && docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit tangerina-test
        echo "Opening coverage report..."
        if command -v xdg-open > /dev/null; then
            xdg-open htmlcov/index.html
        elif command -v open > /dev/null; then
            open htmlcov/index.html
        else
            echo "Coverage report generated at htmlcov/index.html"
        fi
        ;;
    clean)
        echo "Cleaning test artifacts..."
        rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        cd deploy && docker-compose -f docker-compose.test.yml down -v
        echo "Cleanup complete!"
        ;;
    *)
        echo "Usage: $0 {all|unit|integration|watch|coverage|clean}"
        echo ""
        echo "Commands:"
        echo "  all          - Run all tests with coverage (default)"
        echo "  unit         - Run only unit tests (fast)"
        echo "  integration  - Run only integration tests"
        echo "  watch        - Run tests in watch mode (auto-rerun on changes)"
        echo "  coverage     - Run tests and open HTML coverage report"
        echo "  clean        - Remove test artifacts"
        exit 1
        ;;
esac
