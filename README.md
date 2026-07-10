# Django PIM CSV

Bulk CSV import for PIM data: categories, products, attributes, and channel configuration.
Companion module to [entirius-django-pim](https://github.com/entirius/entirius-django-pim).

## Quick Start

Requires Python 3.11+.

```bash
make install                     # uv sync, incl. extras
make test                        # pytest (smoke imports, sqlite)
```

### Other commands

```bash
make check    # ruff check + format-check
make fix      # auto-fix lint + format
```

## Usage

Add `django_pim_csv` to `INSTALLED_APPS` (requires `django_pim`). Imports run via management commands,
e.g.:

```bash
python manage.py products-import-from-csv <shop_idx> <file_path>
python manage.py categories-import-from-csv <shop_idx> <file_path>
```

## Details

See `AGENTS.md` for architecture, importer lifecycle, and CSV column conventions.
