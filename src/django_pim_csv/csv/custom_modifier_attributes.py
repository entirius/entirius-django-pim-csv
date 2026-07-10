# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")
COL_SKU = "sku"
COL_FEATURE_IDX = "feature_idx"
COL_ATTRIBUTE_IDX = "attribute_idx"
COL_GROUP_IDX = "group_idx"
COL_FEATURE_MODIFIED_IDX = "feature_modified_idx"
COL_ATTRIBUTE_MODIFIED_IDX = "attribute_modified_idx"
COL_ATTRIBUTE_COERCED_IDX = "attribute_coerce_idx"
COL_TYPE = "type"
COL_HASH = "hash"


class CustomModifierAttributesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Custom Modifier Attributes CSV"
        self.cols = [
            COL_SKU,
            COL_FEATURE_IDX,
            *[f"{COL_ATTRIBUTE_IDX}_{idx}" for idx in range(0, 10)],
            COL_FEATURE_MODIFIED_IDX,
            *[f"{COL_GROUP_IDX}_{idx}" for idx in range(0, 10)],
            COL_ATTRIBUTE_MODIFIED_IDX,
            COL_TYPE,
            COL_HASH,
        ]
        self.load_all_cols = True
        self.cols_required = [COL_TYPE]
