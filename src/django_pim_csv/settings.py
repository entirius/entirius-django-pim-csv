# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.conf import settings

DEBUG = getattr(settings, "DEBUG", False)

BI_BUSINESS_UNIT = getattr(settings, "BI_BUSINESS_UNIT", "default")
TMP_DIR = getattr(settings, "TMP_DIR", "tmp")
# Bundle
BUNDLE_SKU_QUANTITY_SEPARATOR = getattr(settings, "BUNDLE_SKU_QUANTITY_SEPARATOR", ";")

# ilosc rownoczesnie pracujacych wątków importera produktow z csv
CSV_IMPORT_PRODUCTS_MAX_WORKERS = getattr(settings, "CSV_IMPORT_PRODUCTS_MAX_WORKERS", 5)
# bulk size
CSV_IMPORT_PRODUCTS_BULK_SIZE = getattr(settings, "CSV_IMPORT_PRODUCTS_BULK_SIZE", 100)

# uzywamy ustawien systemowych
T9N_DEFAULT_LANG = settings.T9N_DEFAULT_LANG

# True: Default lang brany jest z PIM.Shop.default_language i moze byc rozny dla roznych kanalow
# False: Default lang brany jest z T9N_DEFAULT_LANG
IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM = getattr(settings, "IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM", False)

SKU_LINK_SEPARATOR = getattr(settings, "SKU_LINK_SEPARATOR", ",")

IMAGE_CATEGORY_SEPARATOR = getattr(settings, "IMAGE_CATEGORY_SEPARATOR", ";")

DATETIME_FORMAT_IMPORT = getattr(settings, "DATETIME_FORMAT_IMPORT", "%Y-%m-%d %H:%M:%S")
ALLOW_CHANGE_PRODUCT_TYPE = getattr(settings, "ALLOW_CHANGE_PRODUCT_TYPE", False)

DELETE_ATTRIBUTES_NOT_IN_CSV = getattr(settings, "DELETE_ATTRIBUTES_NOT_IN_CSV", False)

SKIP_LINKING_PRODUCTS_DEFAULT = getattr(settings, "SKIP_LINKING_PRODUCTS_DEFAULT", False)
SKIP_PICTURES_DEFAULT = getattr(settings, "SKIP_PICTURES_DEFAULT", False)
SKIP_FILES_DEFAULT = getattr(settings, "SKIP_FILES_DEFAULT", False)
IMPORT_PRODUCTS_PIM_CSV_SKIP_FEATURES_INFO = getattr(settings, "IMPORT_PRODUCTS_PIM_CSV_SKIP_FEATURES_INFO", False)
