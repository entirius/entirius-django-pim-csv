# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

Sheet_Config_Channels = "channels"

COL_IDX = "idx"
COL_SCOPE = "scope"
COL_TYPE = "type"
COL_IS_REQUIRED = "required"
COL_IS_FILTERABLE = "filterable"
COL_IS_SEARCHABLE = "searchable"
COL_IS_COMPARABLE = "comparable"
COL_FRONTEND_INPUT_TYPE = "frontend_input_type"
COL_IS_VISIBLE = "visible"


class ConfigFeaturesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "PIM Config Features CSV"
        self.cols = [
            COL_IDX,
            COL_SCOPE,
            COL_TYPE,
            COL_IS_REQUIRED,
            COL_IS_FILTERABLE,
            COL_IS_SEARCHABLE,
            COL_IS_COMPARABLE,
            COL_FRONTEND_INPUT_TYPE,
            COL_IS_VISIBLE,
        ]
        self.cols_required = [COL_IDX, COL_TYPE, COL_IS_FILTERABLE, COL_IS_SEARCHABLE]
