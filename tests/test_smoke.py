# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Smoke test: every public submodule imports cleanly under a configured Django."""

import importlib

import pytest

MODULES = [
    "django_pim_csv.apps",
    "django_pim_csv.bi",
    "django_pim_csv.settings",
    "django_pim_csv.csv.attributes",
    "django_pim_csv.csv.categories",
    "django_pim_csv.csv.common",
    "django_pim_csv.csv.config_channels",
    "django_pim_csv.csv.config_features",
    "django_pim_csv.csv.config_features_in_features_sets",
    "django_pim_csv.csv.config_features_sets",
    "django_pim_csv.csv.custom_modifier_attributes",
    "django_pim_csv.csv.product_attribute_images",
    "django_pim_csv.csv.products",
    "django_pim_csv.csv.products_position",
    "django_pim_csv.worker.abstract",
    "django_pim_csv.worker.attributes_importer",
    "django_pim_csv.worker.categories_importer",
    "django_pim_csv.worker.config_channels_importer",
    "django_pim_csv.worker.config_features_importer",
    "django_pim_csv.worker.config_features_in_features_sets_importer",
    "django_pim_csv.worker.config_features_sets_importer",
    "django_pim_csv.worker.custom_modifiers_attributes_importer",
    "django_pim_csv.worker.product_attribute_images_importer",
    "django_pim_csv.worker.products_importer",
    "django_pim_csv.worker.products_position_importer",
    "django_pim_csv.worker.products_type_importer.products_base",
    "django_pim_csv.worker.products_type_importer.products_bundle",
    "django_pim_csv.worker.products_type_importer.products_config",
    "django_pim_csv.worker.products_type_importer.products_custom",
    "django_pim_csv.worker.products_type_importer.products_simple",
    "django_pim_csv.management.commands.attributes-import-from-csv",
    "django_pim_csv.management.commands.categories-import-from-csv",
    "django_pim_csv.management.commands.config-load-pim-channels",
    "django_pim_csv.management.commands.config-load-pim-feature-position-in-features-sets",
    "django_pim_csv.management.commands.config-load-pim-features",
    "django_pim_csv.management.commands.config-load-pim-features-sets",
    "django_pim_csv.management.commands.csv-remove-columns",
    "django_pim_csv.management.commands.custom-modifiers-attributes-import-from-csv",
    "django_pim_csv.management.commands.product-attribute-images-import-from-csv",
    "django_pim_csv.management.commands.products-import-from-csv",
    "django_pim_csv.management.commands.products-position-import-from-csv",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
