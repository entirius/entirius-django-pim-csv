# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from .common import CommonCsv

logger = logging.getLogger("django")

# Sheet_Simple = "simple"
# Sheet_Configurable = "configurable"

COL_SKU = "sku"
COL_FeatureSet = "feature set"
COL_FeatureSetCustom = "feature set custom"
COL_ProductType = "product type"
COL_Category = "category"
COL_Weight = "weight"
COL_KindOfProduct = "kind of product"
COL_Width = "width"
COL_Height = "height"
COL_Deep = "deep"
COL_Visibility = "visibility"
COL_Enabled = "enabled"
COL_Images = "images"
COL_ImgMain = "img main"
COL_Img_General_1 = "img 1"
COL_Img_General_2 = "img 2"
COL_Link_CrossSell = "linked cross sell"
COL_Link_UpSell = "linked up sell"
COL_Link_Related = "linked related"
COL_Link_Navigation = "linked navigation"
COL_Link_Unknown = "linked unknown"
COL_Files = "files"
COL_FilesCategory = "files categories"
COL_FilesLabel = "files labels"


COL_SourceProductSku = "source product sku"

COL_ConfigurableSku = "config sku"
COL_BundleSku = "bundle sku"
COL_BundleSectionIdx = "bundle idx"
COL_ConfigurableFeature = "config features"


class ProductsCsv(CommonCsv):
    def __init__(self):
        super().__init__()
        self.name = "Products CSV"
        self.cols = [
            COL_SKU,
            COL_FeatureSet,
            COL_ProductType,
            COL_ConfigurableSku,
            COL_BundleSku,
            COL_BundleSectionIdx,
            COL_ConfigurableFeature,
            COL_Category,
            COL_Visibility,
            COL_Weight,
            COL_Width,
            COL_Height,
            COL_Deep,
            COL_Images,
            COL_ImgMain,
            COL_Img_General_1,
            COL_Img_General_2,
            COL_Link_CrossSell,
            COL_Link_UpSell,
            COL_Link_Related,
            COL_Link_Navigation,
            COL_Link_Unknown,
            COL_Files,
            COL_FilesCategory,
            COL_FilesLabel,
        ]
        self.cols_required = [COL_SKU]
