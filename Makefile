.PHONY: setup
setup:
	uv sync
	@echo "🎉 Development environment setup complete!"

.PHONY: sync
sync:
	uv sync --all-extras --all-packages --group dev

.PHONY: format
format:
	uv run ruff format
	uv run ruff check --fix

.PHONY: format-check
format-check:
	uv run ruff format --check

.PHONY: lint
lint:
	uv run ruff check

.PHONY: mypy
mypy:
	uv run mypy .