# Contributing to CAP-IPAWS Bridge

## Development Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pytest ruff
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/test_routing_e2e.py -v  # Integration tests
```

## Code Style

- PEP 8 with 100 char line length
- Type hints on all public functions
- Docstrings on modules, classes, and public methods
- Use `logging` module for output

## Commit Conventions

```
feat(scope): new feature
fix(scope): bug fix
test(scope): tests
docs(scope): documentation
```

### Scopes
`cap`, `ipaws`, `routing`, `dedup`, `audit`, `api`, `feeds`, `admin`
