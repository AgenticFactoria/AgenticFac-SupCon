## Installing new packages

- All new installations should use `uv add`

## Testing

- This project does not use Pytest, only excute ruff formatting
- Consistent style: code formatted with `uv run ruff format`, imports sorted, and type hints passing `uv run mypy .`.
