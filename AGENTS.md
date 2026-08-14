# Repository Instructions

- Use `uv` for Python dependency and test workflows.
- Do not install into the system Python environment.
- Use the repo-local virtual environment at `.venv` when needed.
- Python 3.14 is the supported development and CI runtime.
- Install and lock development dependencies with `uv sync --locked --all-groups`.
- Run lint with `uv run --locked ruff check custom_components/moonside tests`.
- Run tests with `PYTHONPATH=. uv run --locked pytest`.
- `PYTHONPATH=.` is required because this repository is not installed as a Python package.
