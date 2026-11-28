# Contributing to Trakt-Rewind

Contributions, bug reports, and feature ideas are welcome!

## Design Principles
1. **Zero external dependencies:** Stick to Python 3.8+ standard library modules only so anyone can run `trakt_rewind.py` without `pip install`.
2. **Safety first:** Never mutate Trakt history silently without honoring the user's sync speed and auto-backup settings.
3. **Privacy:** Never commit `trakt_token.json`, `trakt_config.json`, `trakt_cache.json`, `trakt_edit_log.json`, or `trakt_backups/`.

## Local Development & Testing
```bash
git clone https://github.com/tokyo720022-create/Trakt-Rewind.git
cd Trakt-Rewind

# Check syntax
python -m py_compile trakt_rewind.py tests/test_trakt_rewind.py

# Run unit test suite
python -m unittest discover -s tests -v
```

## Submitting a Pull Request
1. Fork the repository and create a descriptive feature branch (`git checkout -b feat/movie-support`).
2. Add or update unit tests in `tests/test_trakt_rewind.py` for any logic changes.
3. Verify all tests pass locally.
4. Open a Pull Request filling out the PR template.
