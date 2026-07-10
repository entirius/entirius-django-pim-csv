# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django_pim.models import (
    BundleLink,
    BundleSection,
    ProductBundle,
    ProductClassEnum,
    ProductSimple,
    RealProduct,
    normalize_sku,
)

from django_pim_csv.csv.products import (
    COL_BundleSectionIdx,
    COL_BundleSku,
)
from django_pim_csv.settings import (
    BUNDLE_SKU_QUANTITY_SEPARATOR,
)
from django_pim_csv.worker.products_type_importer.products_base import ProductsImportBase

logger = logging.getLogger("django")


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "prawda")


class ProductsBundleImporter(ProductsImportBase):
    associated_skus_column = COL_BundleSku
    product_type = ProductClassEnum.ProductBundle
    name = "bundle"
    model = ProductBundle
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
        product = ProductBundle.objects.filter(real_product=real_product, shop=self.importer.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Simple", "sku": sku, "is_created": False}
        self.importer.import_product_features_t9n_only(csv, row=row, product=product)
        return report

    def get_subproducts_skus_bundle(self, csv, row, col) -> dict:
        subproducts_skus = {}
        skus_raw = csv.get_row_value(row, col)
        if not skus_raw:
            return {}
        for sku_raw in str(skus_raw).split(","):
            try:
                parts = str(sku_raw).split(BUNDLE_SKU_QUANTITY_SEPARATOR)
                sku = normalize_sku(parts[0])
                if not sku:
                    continue
                quantity = int(parts[1]) if len(parts) > 1 else 1
                is_required = _parse_bool(parts[2]) if len(parts) > 2 else False
                is_default = _parse_bool(parts[3]) if len(parts) > 3 else False
                can_change_quantity = _parse_bool(parts[4]) if len(parts) > 4 else True
                subproducts_skus[sku] = {
                    "quantity": quantity,
                    "is_required": is_required,
                    "is_default": is_default,
                    "can_change_quantity": can_change_quantity,
                }
            except (IndexError, ValueError):
                continue
        return subproducts_skus

    def import_product_subproducts_bundle(self, csv, row, bundle_product):
        subproducts_data = self.get_subproducts_skus_bundle(csv, row, COL_BundleSku)
        bundle_section_idx = csv.get_row_value(row, COL_BundleSectionIdx)

        if not subproducts_data:
            if not self.importer.update_only:
                self.importer.error(
                    f"Bundle Product sku={bundle_product.sku} has no subproducts skus defined in csv col={COL_BundleSku}"
                )
            return
        real_subproducts = RealProduct.objects.filter(sku__in=subproducts_data.keys())
        if len(real_subproducts) == 0:
            self.importer.error(
                f'Can not find subproducts for Bundle Product sku={bundle_product.sku} and subproducts_skus="{subproducts_data.keys()}"'
            )
            return

        for real_subproduct in real_subproducts:
            try:
                bundle_section = BundleSection.objects.get(idx=bundle_section_idx)
            except BundleSection.DoesNotExist:
                bundle_section = BundleSection(idx=bundle_section_idx, name=bundle_section_idx)
                bundle_section.save()

            try:
                subproduct = ProductSimple.objects.get(real_product=real_subproduct, shop=self.importer.shop)
                meta = subproducts_data.get(subproduct.sku, {"quantity": 1})
                BundleLink.objects.update_or_create(
                    product_bundle=bundle_product,
                    subproduct=subproduct,
                    defaults={
                        "quantity": meta.get("quantity", 1) if isinstance(meta, dict) else meta,
                        "section": bundle_section,
                        "is_required": meta.get("is_required", False) if isinstance(meta, dict) else False,
                        "is_default": meta.get("is_default", False) if isinstance(meta, dict) else False,
                        "can_change_quantity": meta.get("can_change_quantity", True)
                        if isinstance(meta, dict)
                        else True,
                    },
                )
                logger.info(f"Bundle Product sku={bundle_product.sku} linked with subproduct sku={subproduct.sku}")

            except ProductSimple.DoesNotExist:
                logger.error(
                    f'Can NOT link BundleProduct="{bundle_product}" with SimpleProduct="{real_subproduct.sku}" '
                    f'because SimpleProduct does not exist in shop="{self.importer.shop.idx}", '
                    f'but RealProduct="{real_subproduct.sku}" does exist'
                )
                continue
            except Exception as e:
                print(f"{e} {real_subproduct}")

    def import_product_type(self, csv, row, import_details: bool = False):
        report, product = super().import_product_type(csv, row, False)
        self.import_product_subproducts_bundle(csv, row=row, bundle_product=product)
        return report

    def import_products_type_bulk(self, csv, rows):
        report_bulk = super().import_products_type_bulk(csv, rows)
        return report_bulk
