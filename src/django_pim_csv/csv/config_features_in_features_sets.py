# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

Sheet_Config_Channels = "channels"

COL_FEATURE = "feature-idx"
COL_FEATURE_SET = "feature-set-idx"
COL_POSITION = "position"


class ConfigFeatureInFeaturesSetsCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "PIM Config Feature in FeaturesSets CSV"
        self.cols = [COL_FEATURE, COL_FEATURE_SET, COL_POSITION]
        self.cols_required = [COL_FEATURE, COL_FEATURE_SET]
