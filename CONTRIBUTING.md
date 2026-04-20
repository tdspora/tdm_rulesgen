# Contributing

Thank you for your interest in **rulesgen**. Contributions are welcome.

## Development setup

- Python **3.11+** (see `.python-version`)
- [uv](https://docs.astral.sh/uv/) for environments and tasks

```bash
uv sync --extra dev
```

## Checks before you open a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Fix formatting if needed:

```bash
uv run ruff format .
```

## Issues

- Use the **bug report** or **feature request** templates under `.github/ISSUE_TEMPLATE/` when you open an issue on GitHub.

## Pull requests

- Describe what changed and why.
- Keep changes focused; unrelated drive-by refactors make review harder.
- Add or update tests when behavior changes.

## License

By contributing, you agree that your contributions will be licensed under the
same terms as this project: **Apache License 2.0** (see `LICENSE` and `NOTICE`).
