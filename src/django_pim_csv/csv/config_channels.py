# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

Sheet_Config_Channels = "channels"

COL_IDX = "idx"
COL_NAME = "name"
COL_DEFAULT_LANGUAGE = "default_language"
COL_LANGUAGES = "languages"
COL_DEFAULT_CURRENCY = "default_currency"
COL_CURRENCIES = "currencies"


class ConfigChannelsCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "PIM Config Channels CSV"
        self.cols = [COL_IDX, COL_NAME, COL_DEFAULT_LANGUAGE, COL_LANGUAGES, COL_DEFAULT_CURRENCY, COL_CURRENCIES]
        self.cols_required = [
            COL_IDX,
            COL_NAME,
            COL_DEFAULT_LANGUAGE,
            COL_LANGUAGES,
            COL_DEFAULT_CURRENCY,
            COL_CURRENCIES,
        ]
