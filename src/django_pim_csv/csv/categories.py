# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

COL_idx = "idx"
COL_Parent = "parent"
COL_External_Id = "external_id"
COL_Is_Active = "is active"
COL_Position = "position"
COL_Is_In_Menu = "is in menu"
COL_ImgMain = "img main"
COL_Extension = "extension"

COL_Base_Name = "name"
COL_Base_Description = "description"
COL_Base_UrlKey = "url key"
COL_Base_MetaTitle = "meta title"
COL_Base_MetaDescription = "meta description"


class CategoriesCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Categories CSV"
        self.cols = [COL_idx, COL_Parent, COL_Is_Active, COL_Position, COL_Is_In_Menu, COL_ImgMain, COL_Extension]
        self.cols_required = [COL_idx, COL_Parent]
