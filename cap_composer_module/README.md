# cap_composer_module

Embedded CAP 1.2 alert authoring engine that ships with the
`cap-ipaws-bridge`. The composer renders a small HTML form, validates the
operator's input against the OASIS enums, and forwards the assembled
payload to the bridge's FastAPI `POST /api/v1/compose` endpoint for
dispatch through IPAWS-OPEN.

## Install

```bash
cd cap_composer_module
pip install -e .                    # bare composer (Django only)
pip install -e .[wagtail]           # optional Wagtail surface
python manage.py runserver          # serves at http://localhost:8000/composer/
```

## Configuration

| Env var                   | Default                                  | Notes |
|---------------------------|------------------------------------------|-------|
| `CAP_BRIDGE_COMPOSE_URL`  | `http://localhost:8000/api/v1/compose`   | Bridge endpoint to forward to. |
| `CAP_COMPOSER_SECRET_KEY` | dev-insecure                             | **Required** in any deployed env. |
| `DJANGO_DEBUG`            | `1`                                      | Set to `0` in production. |
| `DJANGO_ALLOWED_HOSTS`    | `localhost,127.0.0.1,0.0.0.0`            | Comma-separated. |

## Layout

```
cap_composer_module/
├── setup.py                         # pip install -e . target
├── manage.py                        # Django entry point
└── cap_composer_app/
    ├── settings.py                  # minimal Django settings
    ├── urls.py                      # /composer, /compose
    ├── views.py                     # GET form + POST forwarder
    ├── cli.py                       # `cap-composer` console script
    └── templates/composer.html      # form UI
```

The composer intentionally does not duplicate the schema-validation logic
that lives in `modules/ipaws/validator.py` — it forwards to the bridge,
which is the single source of truth for what counts as a valid CAP 1.2
alert.
