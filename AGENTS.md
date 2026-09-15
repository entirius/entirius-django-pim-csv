# AGENTS.md

Bulk CSV importer for PIM data: categories, products, attributes, prices, quantities — distribution
`entirius-django-pim-csv`, Django app `django_pim_csv`. Reads CSV files, validates, and writes to
django-pim models via Django ORM.

**Tech:** Python >=3.11, Django >=5.0, entirius-django-pim

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_pim_csv` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.

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

## File Map

| Path | Purpose |
|------|---------|
| `src/django_pim_csv/csv/common.py` | Base CSV parser — header discovery, type conversion, iteration |
| `src/django_pim_csv/csv/categories.py` | Category CSV column definitions |
| `src/django_pim_csv/csv/products.py` | Product CSV columns (126 columns) |
| `src/django_pim_csv/csv/attributes.py` | Attribute CSV columns |
| `src/django_pim_csv/csv/products_position.py` | Product position columns |
| `src/django_pim_csv/csv/config_*.py` | Configuration CSV columns (channels, features, feature sets) |
| `src/django_pim_csv/worker/abstract.py` | AbstractSync base class — lock, config, t9n, progress |
| `src/django_pim_csv/worker/categories_importer.py` | Category hierarchy import with t9n validation |
| `src/django_pim_csv/worker/products_importer.py` | Product import orchestrator (1694 lines) |
| `src/django_pim_csv/worker/attributes_importer.py` | Attribute value import |
| `src/django_pim_csv/worker/products_type_importer/` | Type-specific: simple, configurable, bundle, custom |
| `src/django_pim_csv/worker/config_*_importer.py` | Configuration importers |
| `src/django_pim_csv/management/commands/` | 10 management commands |
| `src/django_pim_csv/settings.py` | All configurable settings with defaults |
| `src/django_pim_csv/bi.py` | Business Intelligence event definitions |

## Key Patterns

### Importer Lifecycle

Every importer follows this sequence:

1. **`__init__()`** — Setup + acquire lock file (`/tmp/_lock_{BI_BUSINESS_UNIT}_csv_import.tmp`)
2. **`configure_csv()`** — Register columns, set up t9n columns from shop languages
3. **`start()`** — Orchestrate: open CSV, validate headers, iterate rows, import each
4. Entity-specific import methods — Create/update Django ORM objects

Management commands instantiate the worker, call chainable setters (`.set_update_only()`,
`.set_delete()`, etc.), then call `.start()`.

### Translation (t9n) Validation

Importers validate that required translation fields are filled for all shop languages. The pattern
uses a `required_t9n_fields` list of tuples.

**To add a new validated t9n field**, append a tuple `(field_key, field_name, hint)` to the list:

```python
required_t9n_fields = [
    ("url_key_t9n", "URL key", "Category will have no URL for these languages"),
    ("name_t9n", "name", "Category will display without a name for these languages"),
]
```

`validate_row()` iterates this list and logs errors with the category idx and row number when
languages are missing. This pattern is established in `categories_importer.py` and should be
replicated in `products_importer.py` when product-level t9n validation is needed.

### `init_langs()` Gotcha

`init_langs()` pulls languages from ALL shops in the system, not just the target shop. This means
t9n dicts get empty strings for languages not in the target shop. `update_value_t9n()` handles this
with a truthy check (`if value:`). Do not remove that check.

### `self.error()` vs `logger.error()`

- **`self.error(msg)`** — Prints to stdout. Use for issues operators should see during import runs.
- **`logger.error(msg)`** — Writes to log file only. Use for technical errors not relevant to operators.
- **`self.info(msg)`** — Stdout progress info. Use sparingly — bulk imports generate noise.

### Adding a New Importer

1. Create CSV class in `csv/new_entity.py`:
   - Inherit `CommonCsv`
   - Define `cols` (all columns) and `cols_required` (must-have columns)
   - Define column constants at module level

2. Create worker in `worker/new_entity_importer.py`:
   - Inherit `AbstractSync`
   - Implement `configure_csv()` and `start()`
   - Use `self.csv` for row iteration, `self.info()`/`self.error()` for output

3. Create management command in `management/commands/new-entity-import-from-csv.py`:
   - Instantiate worker, call setters, call `.start()`
   - Follow existing argument patterns (`shop_idx`, `file_path`, `--update-only`, `--limit`)

### CSV Column Definition Pattern

Each CSV type defines columns as module-level constants, then registers them:

```python
COL_idx = "idx"
COL_Parent = "parent"
COL_is_enabled = "is_enabled"

class CategoriesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Categories CSV"
        self.cols = [COL_idx, COL_Parent, COL_is_enabled, ...]
        self.cols_required = [COL_idx, COL_Parent]
```

Translation columns are added dynamically at runtime based on shop languages: `"name en"`, `"name pl"`, etc.

### Product Type Dispatch

`products_importer.py` detects product type from the `product type` CSV column and delegates to:
- `ProductsSimpleImporter` — standard products
- `ProductsConfigurableImporter` — parent with variants (uses `config_features`, `config_sku`)
- `ProductsBundleImporter` — bundle products (uses `bundle_sku`, `bundle_idx`)
- `ProductsCustomImporter` — custom product type

All inherit from `ProductsImportBase` in `products_type_importer/products_base.py`.

## Module Conventions

- **`normalize_idx(value)`** — Call for all idx values before DB lookup. Uses `entirius-py-idx-normalizator`.
- **`normalize_sku(value)`** — Call for all SKU values. Strips whitespace, lowercases.
- **`update_or_create` pattern** — All importers use Django's `update_or_create` for idempotent imports.
- **Lock file** — One lock per business unit. Prevents concurrent imports. Located at
  `/tmp/_lock_{BI_BUSINESS_UNIT}_csv_import.tmp`.
- **Decimal parsing** — `price_to_decimal()` handles Magento formats: `"14 000,45"`, `"39.000000"`,
  `"17,5"` all normalize to proper Decimals.
- **Boolean parsing** — Recognizes: `"yes"`, `"true"`, `"1"`, `"prawda"` (Polish for "true").
- **Separator conventions** — SKU links: `,`, bundle SKU:qty: `;`, image main:category: `;`, categories: `,` or `;`.

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

## Dependencies

Core: `entirius-django-pim`, `entirius-django-regional`, `entirius-django-utils`,
`entirius-py-lockfile`, `entirius-py-bievents`, `entirius-py-idx-normalizator`.

## User-Facing Documentation

Usage guides, CSV format specs, and command reference live in
[entirius-docs](https://docs.entirius.com/volkanos/modules/pim-csv/). This AGENTS.md covers
development patterns only.
