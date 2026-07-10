# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import BiEventAbstract
from django.conf import settings

BI_SOURCE = "django-pim-csv"
BI_ENVIRONMENT = settings.BI_ENVIRONMENT
BI_BUSINESS_UNIT = settings.BI_BUSINESS_UNIT


class EventAbstract(BiEventAbstract):
    details_type = "Event Abstract"
    version = 1

    def __init__(self, **kwargs):
        kwargs["source"] = BI_SOURCE
        kwargs["environment"] = BI_ENVIRONMENT
        kwargs["business_unit"] = BI_BUSINESS_UNIT
        super().__init__(**kwargs)


class ProductImportFromCsvEvent(EventAbstract):
    details_type = "Product Import From Csv"
    version = 1

    def __init__(self, file_path, shop, sku, **kwargs):
        details = {
            "file_path": file_path,
            "shop": shop,
            "sku": sku,
            "product_type": None,
            "is_created": None,
            # "is_updated": None, #TODO
        }
        super().__init__(details=details, **kwargs)


class ProductsImportFromCsvStartEvent(EventAbstract):
    details_type = "Product Import From Csv Start"
    version = 1
    is_ongoing_event = False

    def __init__(self, file_path, shop, **kwargs):
        details = {"file_path": file_path, "shop": shop}
        super().__init__(details=details, **kwargs)


class ProductsImportFromCsvEndEvent(EventAbstract):
    details_type = "Product Import From Csv End"
    version = 1
    is_ongoing_event = True

    def __init__(self, file_path, shop, **kwargs):
        details = {"file_path": file_path, "shop": shop}
        super().__init__(details=details, **kwargs)


class ProductsBulkImportFromCsvEvent(EventAbstract):
    details_type = "Products Bulk Import From Csv"
    version = 1
    is_ongoing_event = True

    def __init__(self, file_path, shop, **kwargs):
        self.details = {
            "file_path": file_path,
            "shop": shop,
            "skus": [],
            "product_type": None,
        }
        super().__init__(**kwargs)


class AttributesImportFromCsvEvent(EventAbstract):
    details_type = "Attributes Import From Csv"
    version = 1

    def __init__(self, file_path, feature_idx, **kwargs):
        self.details = {
            "file_path": file_path,
            "feature_idx": feature_idx,
            "count_processed_rows": None,
            "count_new": None,
        }
        super().__init__(**kwargs)


class CustomModifierAttributesImportFromCsvEvent(EventAbstract):
    details_type = "Custom Modifier Attributes Import From Csv"
    version = 1

    def __init__(self, file_path, **kwargs):
        self.details = {
            "file_path": file_path,
            "count_processed_rows": None,
            "count_new": None,
        }
        super().__init__(**kwargs)


class CategoriesImportFromCsvEvent(EventAbstract):
    version = 1
    details_type = "Categories Import From Csv"

    def __init__(self, file_path, shop, **kwargs):
        self.details = {
            "file_path": file_path,
            "shop": shop,
            "count_processed_rows": None,
            "count_new": None,
        }
        super().__init__(**kwargs)


class ConfigImportFromCsvEvent(EventAbstract):
    details_type = "Config Import From Csv"
    version = 1
    is_ongoing_event = True

    def __init__(self, file_path, **kwargs):
        self.details = {
            "file_path": file_path,
            "count_processed_rows": None,
            "count_new": None,
        }
        super().__init__(**kwargs)


class ConfigFeaturesInFeaturesSetsFromCsvEvent(EventAbstract):
    details_type = "Config Features In Features Sets Importer"
    version = 1
    is_ongoing_event = True

    def __init__(self, file_path, **kwargs):
        self.details = {
            "file_path": file_path,
            "count_processed_rows": None,
            "count_new": None,
        }
        super().__init__(**kwargs)
