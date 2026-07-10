# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

COL_IDX = "idx"
COL_SKU = "sku"
COL_IMAGES = "images"
IMAGES_SEPARATOR = ","
COL_COLOR_HASH = "color_hash"


class ProductAttributeImagesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Product Attribute Images CSV"
        self.cols = [COL_IDX, COL_SKU, COL_IMAGES, COL_COLOR_HASH]
        self.cols_required = [COL_IDX, COL_SKU]
