# Contributing

Thanks for helping improve Jarvis.

## Development workflow

1. Create a focused branch from the default branch.
2. Create a Python 3.11 virtual environment.
3. Install the project with `python -m pip install -e '.[dev]'`.
4. Run `pre-commit install`.
5. Add or update tests for behavioral changes.
6. Run `ruff check --no-fix .` and `pytest` before opening a pull request.

Keep pull requests focused and explain hardware or OS assumptions in the
description.

## Privacy and generated files

Never commit API keys, passwords, logs, recordings, personal photos, biometric
encodings, runtime JSON files, desktop indexes, model checkpoints, or notebook
outputs containing personal data. Use synthetic fixtures for tests and examples.

Only submit a person's image or voice recording when you have explicit permission
to publish it under this repository's license.
