# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

Sheet_Attributes = "attributes"

COL_IDX = "idx"
COL_EXT = "extension"
COL_GROUP_IDX = "group_idx"
COL_DISPLAY_ORDER = "display_order"
COL_EXT = "extension"


class AttributesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Attributes CSV"
        self.cols = [COL_IDX, COL_GROUP_IDX, COL_DISPLAY_ORDER]
        self.cols_required = [COL_IDX]
