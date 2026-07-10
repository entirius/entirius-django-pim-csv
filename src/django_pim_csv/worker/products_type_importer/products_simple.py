# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django_pim.models import (
    ProductClassEnum,
    ProductSimple,
    RealProduct,
)

from .products_base import ProductsImportBase

logger = logging.getLogger("django")


class ProductsSimpleImporter(ProductsImportBase):
    associated_skus_column = None
    product_type = ProductClassEnum.ProductSimple
    name = "simple"
    model = ProductSimple
    importer = None

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
        product = ProductSimple.objects.filter(real_product=real_product, shop=self.importer.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Simple", "sku": sku, "is_created": False}
        self.importer.import_product_features_t9n_only(csv, row=row, product=product)
        return report

    def import_product_type(self, csv, row, import_details: bool = False):
        report, product = super().import_product_type(csv, row, True)
        return report

    def import_products_type_bulk(self, csv, rows):
        report_bulk = super().import_products_type_bulk(csv, rows)
        return report_bulk
