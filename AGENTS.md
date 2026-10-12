# AGENTS.md

`entirius-django-pim-csv` (Django app `django_pim_csv`) — bulk CSV importer of Entirius for PIM data: categories,
products, attributes, prices, quantities. Reads CSV files, validates, and writes to
django-pim models via Django ORM.

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

Tests need PostgreSQL: set `DATABASE_URL` (the default in `tests/settings.py` points at a local postgres).

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_pim_csv` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.
- No AI attribution in commits or PR descriptions.

## Architecture

```
Management Command (CLI)
  → Worker (business logic, inherits AbstractSync)
    → CSV layer (column definitions, parsing, type conversion)
      → Django ORM (django-pim models)
```

Each entity type (categories, products, attributes, config) has:
1. A **CSV class** in `csv/` defining columns
2. A **worker** in `worker/` implementing import logic
3. A **management command** in `management/commands/` wiring CLI to worker

Products have an additional sub-layer: type-specific importers in `worker/products_type_importer/`
(simple, configurable, bundle, custom).

| Path | Purpose |
|------|---------|
| `src/django_pim_csv/csv/common.py` | Base CSV parser — header discovery, type conversion, iteration |
| `src/django_pim_csv/csv/categories.py` | Category CSV column definitions |
| `src/django_pim_csv/csv/products.py` | Product CSV columns |
| `src/django_pim_csv/csv/attributes.py` | Attribute CSV columns |
| `src/django_pim_csv/csv/products_position.py` | Product position columns |
| `src/django_pim_csv/csv/config_*.py` | Configuration CSV columns (channels, features, feature sets) |
| `src/django_pim_csv/worker/abstract.py` | AbstractSync base class — lock, config, t9n, progress |
| `src/django_pim_csv/worker/categories_importer.py` | Category hierarchy import with t9n validation |
| `src/django_pim_csv/worker/products_importer.py` | Product import orchestrator |
| `src/django_pim_csv/worker/attributes_importer.py` | Attribute value import |
| `src/django_pim_csv/worker/products_type_importer/` | Type-specific: simple, configurable, bundle, custom |
| `src/django_pim_csv/worker/config_*_importer.py` | Configuration importers |
| `src/django_pim_csv/management/commands/` | Management commands (kebab-case filenames) |
| `src/django_pim_csv/settings.py` | All configurable settings with defaults |
| `src/django_pim_csv/bi.py` | Business Intelligence event definitions |

Importer lifecycle: `__init__()` (setup + lock file) → `configure_csv()` (columns, t9n columns from shop languages)
→ `start()` (open CSV, validate headers, iterate rows). Management commands instantiate the worker, call chainable
setters (`.set_update_only()`, `.set_delete()`, …), then `.start()`. Product rows dispatch by the `product type`
column to the importers in `worker/products_type_importer/`.

Module conventions:

- **`normalize_idx(value)`** — Call for all idx values before DB lookup. Uses `entirius-py-idx-normalizator`.
- **`normalize_sku(value)`** — Call for all SKU values. Strips whitespace, lowercases.
- **`update_or_create` pattern** — All importers use Django's `update_or_create` for idempotent imports.
- **Lock file** — One lock per business unit. Prevents concurrent imports. Located at
  `/tmp/_lock_{BI_BUSINESS_UNIT}_csv_import.tmp`.
- **Decimal parsing** — `price_to_decimal()` handles Magento formats: `"14 000,45"`, `"39.000000"`,
  `"17,5"` all normalize to proper Decimals.
- **Boolean parsing** — Recognizes: `"yes"`, `"true"`, `"1"`, `"prawda"` (Polish for "true").
- **Separator conventions** — SKU links: `,`, bundle SKU:qty: `;`, image main:category: `;`, categories: `,` or `;`.

| Topic | Where |
|---|---|
| Overview, supported entity types, import order | `docs/index.md` |
| Import modes, ordering, error handling, concurrency, importer internals (lifecycle, t9n validation, adding an importer) | `docs/import-pipeline.md` |
| CSV columns and naming conventions | `docs/csv-format.md` |
| Management commands | `docs/commands.md` |
| Usage guides | https://docs.entirius.com/ |

## Settings

All settings read from Django settings via `settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `T9N_DEFAULT_LANG` | (required) | Default language for translations |
| `IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM` | `False` | Use shop's default language vs global |
| `CSV_IMPORT_PRODUCTS_MAX_WORKERS` | `5` | Thread pool size for product import |
| `CSV_IMPORT_PRODUCTS_BULK_SIZE` | `100` | Batch size for bulk DB operations |
| `BUNDLE_SKU_QUANTITY_SEPARATOR` | `";"` | Separator in bundle SKU:qty pairs |
| `SKU_LINK_SEPARATOR` | `","` | Separator for linked product SKUs |
| `ALLOW_CHANGE_PRODUCT_TYPE` | `False` | Allow changing existing product type |
| `DELETE_ATTRIBUTES_NOT_IN_CSV` | `False` | Delete attributes of the imported feature that the CSV does not list |
| `SKIP_LINKING_PRODUCTS_DEFAULT` | `False` | Skip product linking by default |
| `SKIP_PICTURES_DEFAULT` | `False` | Skip image import by default |
| `SKIP_FILES_DEFAULT` | `False` | Skip file import by default |

## Gotchas

- `init_langs()` pulls languages from ALL shops, not just the target shop: t9n dicts get empty strings for the
  other languages. `update_value_t9n()` handles this with a truthy check (`if value:`) — do not remove it.
- `self.error(msg)` / `self.info(msg)` print to stdout for the operator running the import; `logger.error(msg)`
  writes to the log file only. Use `self.info()` sparingly — bulk imports generate noise.
- `T9N_DEFAULT_LANG` has no default: `settings.py` reads it at import time and fails when it is unset.
