# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

COL_SKU = "sku"
COL_CATEGORY = "category_idx"
COL_POSITION = "position"


class ProductsPositionCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Products Position CSV"
        self.cols = [COL_SKU, COL_CATEGORY, COL_POSITION]
        self.cols_required = [COL_SKU, COL_CATEGORY, COL_POSITION]
