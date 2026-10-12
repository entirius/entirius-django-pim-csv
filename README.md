# entirius-django-pim-csv

A Django module for bulk CSV import into the product catalog of Entirius, the open-source modular ecommerce platform.
It loads categories, products, attributes and channel configuration into the models of `entirius-django-pim`
through management commands.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-pim-csv.svg)](https://pypi.org/project/entirius-django-pim-csv/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-pim-csv.svg)](https://pypi.org/project/entirius-django-pim-csv/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-pim-csv/blob/develop/LICENSE)

## What it does

- Imports categories, products, attribute values, product positions and attribute images from CSV files.
- Handles simple, configurable, bundle and custom products in one products file.
- Loads channel configuration: channels, features, feature sets and feature positions.
- Validates headers and required translation columns for every language of the target channel.
- Runs imports idempotently (update or create), with update-only, delete and row-limit modes.
- Holds a lock file per business unit so that two imports never run at once.

## Installation

```shell
uv add entirius-django-pim-csv
pip install entirius-django-pim-csv
```

```python
INSTALLED_APPS = [
    ...
    "django_regional",
    "django_utils",
    "django_pim",
    "django_pim_csv",
]

T9N_DEFAULT_LANG = "en"
```

```shell
python manage.py categories-import-from-csv <shop_idx> <file_path>
python manage.py products-import-from-csv <shop_idx> <file_path>
```

Required setting: `T9N_DEFAULT_LANG`; the module has no URLs. Settings reference with defaults in
https://github.com/entirius/entirius-django-pim-csv/blob/develop/AGENTS.md (section Settings).

## Quick start

```python
from django.core.management import call_command

call_command("categories-import-from-csv", "default", "import/categories.csv")
call_command("products-import-from-csv", "default", "import/products.csv")
```

## Requirements

- Python 3.11 or newer, Django 5.0 or newer.
- PostgreSQL (the test suite runs on it through `DATABASE_URL`).
- Entirius packages pulled in: `entirius-django-pim`, `entirius-django-regional`, `entirius-django-utils`,
  `entirius-py-lockfile`, `entirius-py-bievents`, `entirius-py-idx-normalizator`.

## Documentation

- Module docs: https://github.com/entirius/entirius-django-pim-csv/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Changelog: https://github.com/entirius/entirius-django-pim-csv/blob/develop/CHANGELOG.md

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos) as the bulk loader of the product catalog.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Sibling modules: https://github.com/entirius/entirius-django-pim, https://github.com/entirius/entirius-django-regional, https://github.com/entirius/entirius-django-utils

## Development

```shell
make install     # sync dependencies (uv)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django, needs PostgreSQL via DATABASE_URL)
```

Development and agent instructions: https://github.com/entirius/entirius-django-pim-csv/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-pim-csv/blob/develop/LICENSE.
