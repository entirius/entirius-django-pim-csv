# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django_pim.models import (
    FeatureSet,
    Product,
    ProductClassEnum,
    ProductCustom,
    RealProduct,
)

from django_pim_csv.csv.products import COL_FeatureSetCustom, COL_SourceProductSku

from .products_base import ProductsImportBase

logger = logging.getLogger("django")


class ProductsCustomImporter(ProductsImportBase):
    associated_skus_column = None
    product_type = ProductClassEnum.ProductCustom
    name = "custom"
    importer = None
    model = ProductCustom

    def create_additional_defaults(self, csv, row, defaults: dict = None):
        f9n_set_custom_idx = csv.get_row_value(row, COL_FeatureSetCustom)
        defaults["customization_feature_set"] = FeatureSet.objects.filter(idx=f9n_set_custom_idx).first()

        source_sku = csv.get_row_value(row, COL_SourceProductSku)
        if source_sku:
            source_real = RealProduct.objects.filter(sku=source_sku).first()
            if source_real:
                defaults["source_product"] = Product.objects.filter(
                    real_product=source_real, shop=self.importer.shop
                ).first()

        return defaults

    def import_product_type(self, csv, row, import_details: bool = False):
        report, product = super().import_product_type(csv, row, True)
        return report

    def import_products_type_bulk(self, csv, rows):
        report_bulk = super().import_products_type_bulk(csv, rows)
        return report_bulk

    def update_translations_only(self, csv, row):
        if not self.importer.update_translations_only:
            raise Exception("update_translations_only_simple() requires self.importer.update_translations_only")
        sku = self.importer.get_product_sku(csv, row)
        if not sku:
            return None
        try:
            real_product = RealProduct.objects.get(sku=sku)
        except RealProduct.DoesNotExist:
            return None
        product = ProductCustom.objects.filter(real_product=real_product, shop=self.importer.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Simple", "sku": sku, "is_created": False}
        self.importer.import_product_features_t9n_only(csv, row=row, product=product)
        return report
