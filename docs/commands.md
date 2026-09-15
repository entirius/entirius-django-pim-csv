---
title: Management Commands
description: Reference for all django-pim-csv management commands with arguments and examples.
---

All imports are executed via Django management commands. Each command maps to a worker class that handles the actual import logic.

## categories-import-from-csv

Import product categories with hierarchy and translations.

```bash
python manage.py categories-import-from-csv <shop_idx> <file_path> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `shop_idx` | yes | Shop/channel identifier (e.g., `test-channel`) |
| `file_path` | yes | Path to categories CSV file |
| `--limit N` | no | Process only first N rows |
| `--delete` | no | Delete categories not present in CSV |
| `-u`, `--update-only` | no | Update existing categories only, skip new ones |

```bash
# Full import
python manage.py categories-import-from-csv test-channel categories-test-channel.csv

# Update existing only
python manage.py categories-import-from-csv test-channel categories-update.csv --update-only

# Delete mode (removes categories not in CSV)
python manage.py categories-import-from-csv test-channel categories-test-channel.csv --delete
```

## products-import-from-csv

Import products with features, images, files, and links. Supports simple, configurable, bundle, and custom product types.

```bash
python manage.py products-import-from-csv <shop_idx> <file_path> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `shop_idx` | yes | Shop/channel identifier |
| `file_path` | yes | Path to products CSV file |
| `-s`, `--skip-pictures` | no | Skip image import |
| `-d`, `--skip-files` | no | Skip file import |
| `--skip-linking` | no | Skip product linking (cross-sell, up-sell, etc.) |
| `--limit N` | no | Process only first N rows |
| `-u`, `--update-only` | no | Update existing products only, skip new ones |
| `--update-translations-only` | no | Update translation fields only |
| `-da`, `--no-delete-attr` | no | Do not delete attributes missing from CSV |

```bash
# Full import
python manage.py products-import-from-csv test-channel products-test-channel.csv

# Update translations only (e.g., adding German descriptions)
python manage.py products-import-from-csv test-channel products-de-update.csv --update-translations-only

# Fast import (skip images and files)
python manage.py products-import-from-csv test-channel products.csv -s -d --skip-linking
```

## attributes-import-from-csv

Import attribute values for a specific feature (e.g., all color values, all size values).

```bash
python manage.py attributes-import-from-csv <feature_idx> <file_path> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `feature_idx` | yes | Feature identifier (e.g., `color`, `size`, `brand`) |
| `file_path` | yes | Path to attributes CSV file |
| `--limit N` | no | Process only first N rows |
| `-u`, `--update-only` | no | Update existing attributes only |
| `--delete_not_in_csv` | no | Delete attributes not present in CSV |

```bash
# Import all color attributes
python manage.py attributes-import-from-csv color attributes-color.csv

# Update brand descriptions in English only
python manage.py attributes-import-from-csv brand update-brand-en.csv --update-only
```

## products-position-import-from-csv

Update product display positions within categories.

```bash
python manage.py products-position-import-from-csv <shop_idx> <file_path> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `shop_idx` | yes | Shop/channel identifier |
| `file_path` | yes | Path to positions CSV file |
| `--limit N` | no | Process only first N rows |

```bash
python manage.py products-position-import-from-csv test-channel products-position-test-channel.csv
```

## product-attribute-images-import-from-csv

Map images to product attributes (e.g., color swatches).

```bash
python manage.py product-attribute-images-import-from-csv <shop_idx> <file_path>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `shop_idx` | yes | Shop/channel identifier |
| `file_path` | yes | Path to attribute images CSV file |

## custom-modifiers-attributes-import-from-csv

Import custom modifier attributes for products.

```bash
python manage.py custom-modifiers-attributes-import-from-csv <file_path> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `file_path` | yes | Path to custom modifiers CSV file |
| `--shop_idx` | no | Shop identifier (optional filter) |
| `--limit N` | no | Process only first N rows |
| `-u`, `--update-only` | no | Update existing only |

## config-load-pim-channels

Load shop/channel configuration (languages, currencies).

```bash
python manage.py config-load-pim-channels <file_path>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `file_path` | yes | Path to channels configuration CSV |

Run this before any other import — channels define available languages and currencies.

## config-load-pim-features

Load feature definitions (attribute types, scopes, frontend input types).

```bash
python manage.py config-load-pim-features <file_path>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `file_path` | yes | Path to features configuration CSV |

The import runs in one transaction. Any rejected row — an unknown type, a scope change on an
existing feature, a database error — rolls the whole file back and exits non-zero with one line
per rejected row. A held import lock also exits non-zero.

## config-load-pim-features-sets

Load feature set definitions (groupings of related features).

```bash
python manage.py config-load-pim-features-sets <file_path> [--prune [--dry-run]]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `file_path` | yes | Path to feature sets configuration CSV |
| `--prune` | no | Detach features the CSV does not list, in the sets the CSV names; other sets are untouched |
| `--dry-run` | no | With `--prune`: list what would be detached, write nothing |

Without `--prune` the import only adds memberships. An unknown feature idx rejects the row;
any rejected row rolls the whole file back and exits non-zero.

## config-load-pim-feature-position-in-features-sets

Map features to feature sets with display order.

```bash
python manage.py config-load-pim-feature-position-in-features-sets <file_path> [--prune [--dry-run]]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `file_path` | yes | Path to feature-in-set mapping CSV |
| `--prune` | no | Remove feature–set pairs the CSV does not list, in the sets the CSV names |
| `--dry-run` | no | With `--prune`: list what would be removed, write nothing |

A pair is a set membership, so `--prune` here also detaches features: give it a CSV that lists
every membership of the sets it names. Rejected rows roll the whole file back and exit non-zero.

## csv-remove-columns

Utility to remove specified columns from a CSV file.

```bash
python manage.py csv-remove-columns <file_path> <columns...>
```

Useful for stripping unwanted columns before import.
