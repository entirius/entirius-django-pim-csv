---
title: PIM CSV
description: Bulk CSV importer for product data — categories, products, attributes, and configuration.
sidebar:
  label: Overview
  collapsed: true
---

django-pim-csv imports product data from CSV files into django-pim models. It handles categories, products (simple, configurable, bundle, custom), attributes, and PIM configuration.

## What It Does

- Imports categories with full hierarchy and translations
- Imports products with images, files, links, and feature values
- Imports attribute values per feature (color, size, brand, etc.)
- Loads PIM configuration (channels, features, feature sets)
- Supports multiple import modes: full, update-only, translations-only, delete

## Architecture

```
Management Command (CLI args)
  → Worker (AbstractSync subclass — business logic)
    → CSV Parser (column definitions, type conversion)
      → Django ORM (django-pim models)
```

Each entity type has three layers:

| Layer | Location | Role |
|-------|----------|------|
| CSV | `csv/*.py` | Column definitions, parsing, validation |
| Worker | `worker/*_importer.py` | Import logic, t9n handling, error reporting |
| Command | `management/commands/*.py` | CLI interface, argument parsing |

Products add a sub-layer with type-specific importers for simple, configurable, bundle, and custom products.

## Supported Entity Types

| Entity | Command | CSV Columns |
|--------|---------|-------------|
| Categories | `categories-import-from-csv` | idx, parent, is_enabled, name, url_key, image |
| Products | `products-import-from-csv` | sku, product_type, category, features, images, links |
| Attributes | `attributes-import-from-csv` | idx, name, extension_json, image |
| Product positions | `products-position-import-from-csv` | sku, category, position |
| Attribute images | `product-attribute-images-import-from-csv` | shop_idx, file_path |
| Custom modifiers | `custom-modifiers-attributes-import-from-csv` | file_path |
| Channels | `config-load-pim-channels` | idx, name, languages, currency |
| Features | `config-load-pim-features` | idx, type, scope, frontend_input |
| Feature sets | `config-load-pim-features-sets` | idx, name, is_default |
| Features in sets | `config-load-pim-feature-position-in-features-sets` | feature_idx, set_idx, position |

## Import Order

Dependencies between entity types dictate the import sequence:

1. **Channels** — `config-load-pim-channels` (shops and languages)
2. **Features** — `config-load-pim-features` (feature definitions)
3. **Feature sets** — `config-load-pim-features-sets` (feature groupings)
4. **Feature positions** — `config-load-pim-feature-position-in-features-sets`
5. **Attributes** — `attributes-import-from-csv` (per feature)
6. **Categories** — `categories-import-from-csv` (per shop)
7. **Products** — `products-import-from-csv` (per shop)
8. **Product positions** — `products-position-import-from-csv` (optional)
9. **Attribute images** — `product-attribute-images-import-from-csv` (optional)

## Translation Handling

CSV columns for translated fields follow the pattern `{field} {lang}`:

```
name en, name pl, name de
short_description en, short_description pl
url_key en, url_key pl
```

Languages are determined from the shop's configured languages. The default language column is required; others are optional.

## Configuration

Key Django settings (all have sensible defaults):

| Setting | Default | Purpose |
|---------|---------|---------|
| `T9N_DEFAULT_LANG` | (required) | Default language for translations |
| `CSV_IMPORT_PRODUCTS_MAX_WORKERS` | `5` | Thread pool size for product import |
| `CSV_IMPORT_PRODUCTS_BULK_SIZE` | `100` | Batch size for bulk operations |
| `ALLOW_CHANGE_PRODUCT_TYPE` | `False` | Allow changing existing product type |

Full settings reference in [AGENTS.md](https://github.com/entirius/entirius-django-pim-csv/blob/master/AGENTS.md).

## Next Steps

- [Management commands reference](/volkanos/modules/pim/pim-csv/commands/)
- [CSV format specification](/volkanos/modules/pim/pim-csv/csv-format/)
- [Import pipeline and modes](/volkanos/modules/pim/pim-csv/import-pipeline/)
- [Changelog](/volkanos/modules/pim/pim-csv/changelog/)
