# Repository Instructions

- Use `uv` for Python dependency and test workflows.
- Do not install into the system Python environment.
- Use the repo-local virtual environment at `.venv` when needed.
- Install test dependencies with `uv pip install --python .venv/bin/python -r requirements-test.txt`.
- Run lint with `uv run --python .venv/bin/python ruff check custom_components/moonside tests`.
- Run tests with `PYTHONPATH=. uv run --python .venv/bin/python pytest`.
- `PYTHONPATH=.` is required because this repo is not packaged with a `pyproject.toml`, so `custom_components` is otherwise not importable under `uv run`.
