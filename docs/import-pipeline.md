---
title: Import Pipeline
description: How CSV imports work end-to-end — modes, ordering, error handling, and concurrency.
---

## How an Import Runs

Every import follows the same lifecycle:

1. **Lock acquisition** — A lock file prevents concurrent imports of the same business unit
2. **CSV parsing** — Headers are analyzed (first 10 rows), required columns validated
3. **Language setup** — Shop languages are fetched, t9n columns are configured
4. **Row iteration** — Each row is processed independently
5. **ORM writes** — `update_or_create` ensures idempotent imports
6. **Lock release** — Lock file is removed on completion

If a lock file already exists, the import exits with a message. This prevents data corruption from overlapping imports.

## Import Modes

### Full Import

The default mode. Imports the entire dataset — creates new objects, updates existing ones, and optionally deletes objects not present in the CSV.

```bash
# Full import with deletion of missing categories
python manage.py categories-import-from-csv test-channel categories.csv --delete

# Full product import
python manage.py products-import-from-csv test-channel products.csv
```

Use for initial data loads and periodic full synchronization (weekly/monthly). The CSV must contain the complete dataset for the scope (shop or feature).

### Update Only

Updates existing objects but does not create new ones. Objects in the CSV that don't exist in the database are silently skipped.

```bash
python manage.py products-import-from-csv test-channel products-update.csv --update-only
python manage.py categories-import-from-csv test-channel categories-update.csv --update-only
python manage.py attributes-import-from-csv color attributes-update.csv --update-only
```

Use for incremental updates — e.g., price changes, description edits, adding translations. The CSV can contain a subset of rows and columns.

### Update Translations Only

Updates only translation fields (name, description, url_key, meta fields) in a specific language. Non-translation columns are ignored.

```bash
python manage.py products-import-from-csv test-channel products-de.csv --update-translations-only
```

Use when adding a new language or correcting translations. The CSV only needs SKU + the language columns being updated.

### Delete Mode

When `--delete` is passed, objects present in the database but absent from the CSV are removed. Only applies to categories (via `--delete`) and attributes (via `--delete_not_in_csv`).

```bash
# Delete categories not in CSV
python manage.py categories-import-from-csv test-channel categories.csv --delete

# Delete attributes not in CSV
python manage.py attributes-import-from-csv color attributes.csv --delete_not_in_csv
```

Use with caution — the CSV must be the complete dataset, not a partial update.

## Import Order Dependencies

Entity types have dependencies that dictate the correct import sequence:

```
Channels → Features → Feature Sets → Feature Positions
                                        ↓
                              Attributes (per feature)
                                        ↓
                              Categories (per shop)
                                        ↓
                              Products (per shop)
                                        ↓
                         Product Positions (optional)
                         Attribute Images (optional)
```

Import channels first — they define available languages. Import features before attributes. Import categories before products (products reference categories).

## Category Hierarchy

Categories are imported with parent-child relationships. The importer:

1. Reads all rows into an in-memory dictionary
2. Calculates tree depth for each category
3. Sorts categories by depth (shallowest first)
4. Imports in order — parents are always created before children

If a category references a parent that doesn't exist in the CSV, the importer creates the parent on demand if it exists in the database. Invalid parent references are skipped with an error log.

## Product Type Handling

The `product_type` column determines how a product is processed:

| Type | Behavior |
|------|----------|
| `simple` (default) | Standard product with direct features and images |
| `config` | Configurable parent — links to child products via `config_sku`, variant axes via `config_features` |
| `bundle` | Bundle product — links to components via `bundle_sku` with quantities |
| `virtual` | Set via `kind_of_product` column — no physical shipping |

One simple product can belong to multiple configurable parents.

## Error Handling

Imports are resilient — a bad row does not stop the import:

- **Missing required columns** — Import fails before processing any rows
- **Bad row data** — Error logged, row skipped, import continues
- **Missing parent category** — Error logged, category skipped
- **Invalid image path** — Warning logged, image skipped, product still imported
- **Type conversion failure** — Returns None, field left empty

Errors are printed to stdout via `self.error()`. Check the terminal output after each import run.

The importer adds `import status` and `import message` columns to the output for categories, allowing post-import review.

## Concurrency

Product imports use multi-threaded processing:

- **Thread pool:** `CSV_IMPORT_PRODUCTS_MAX_WORKERS` threads (default: 5)
- **Bulk size:** `CSV_IMPORT_PRODUCTS_BULK_SIZE` rows per batch (default: 100)
- **Lock file:** One import per business unit at a time

Other importers (categories, attributes, config) run single-threaded.

## Skipping Features

Product imports can skip expensive operations:

```bash
# Skip all images
python manage.py products-import-from-csv test-channel products.csv -s

# Skip downloadable files
python manage.py products-import-from-csv test-channel products.csv -d

# Skip product linking (cross-sell, up-sell, related)
python manage.py products-import-from-csv test-channel products.csv --skip-linking

# Combine for fastest import (data only)
python manage.py products-import-from-csv test-channel products.csv -s -d --skip-linking
```

Default skip behavior is configurable via Django settings: `SKIP_PICTURES_DEFAULT`, `SKIP_FILES_DEFAULT`, `SKIP_LINKING_PRODUCTS_DEFAULT`.

## Column Filtering

The `COLS_TO_UPDATE_CATEGORIES` and `COLS_TO_UPDATE_PRODUCTS` settings control which columns are updated during import. By default, all columns in the CSV are processed. Set these to restrict updates to specific fields:

```python
# settings.py — only update names during category import
COLS_TO_UPDATE_CATEGORIES = ["name"]

# Only update descriptions and brand during product import
COLS_TO_UPDATE_PRODUCTS = ["short_description", "brand", "diameter"]
```

## Typical Workflows

### Initial Setup (New Deployment)

```bash
# Load fixtures
python manage.py loaddata regional-defaults.yaml
python manage.py loaddata common-pim-config.yaml
python manage.py loaddata pim-config.yaml

# Import in order
python manage.py config-load-pim-channels channels.csv
python manage.py config-load-pim-features features.csv
python manage.py config-load-pim-features-sets feature-sets.csv
python manage.py attributes-import-from-csv color attributes-color.csv
python manage.py attributes-import-from-csv size attributes-size.csv
python manage.py categories-import-from-csv test-channel categories.csv
python manage.py products-import-from-csv test-channel products.csv
```

### Weekly Full Sync

```bash
python manage.py categories-import-from-csv test-channel categories.csv --delete
python manage.py products-import-from-csv test-channel products.csv
```

### Adding a New Language

```bash
# Update attributes with new language columns
python manage.py attributes-import-from-csv color attributes-color-de.csv --update-only

# Update categories
python manage.py categories-import-from-csv test-channel categories-de.csv --update-only

# Update products (translations only)
python manage.py products-import-from-csv test-channel products-de.csv --update-translations-only
```

## BI Events

Each import emits business intelligence events:

| Event | When |
|-------|------|
| `ProductsImportFromCsvStartEvent` | Product import begins |
| `ProductsImportFromCsvEndEvent` | Product import completes |
| `ProductsBulkImportFromCsvEvent` | Progress tracking during import |
| `CategoriesImportFromCsvEvent` | Category import completes |
| `AttributesImportFromCsvEvent` | Attribute import completes |
| `ConfigImportFromCsvEvent` | Config import completes |

Events include: source (`django-pim-csv`), environment, business unit, file path, shop, and row counts.

## Importer Internals

Patterns for changing or adding an importer.

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
