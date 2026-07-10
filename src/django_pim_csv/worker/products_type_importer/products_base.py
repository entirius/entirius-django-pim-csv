# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.db.utils import IntegrityError
from django_pim.models import ProductClassEnum, ProductVisibilityEnum, RealProduct

from django_pim_csv.bi import ProductsBulkImportFromCsvEvent
from django_pim_csv.csv.products import (
    COL_Deep,
    COL_Enabled,
    COL_Height,
    COL_Visibility,
    COL_Weight,
    COL_Width,
)

logger = logging.getLogger("django")


class ProductsImportBase:
    associated_skus_column = None
    product_type: ProductClassEnum = None
    model = None
    name = None
    importer = None
    additional_defaults = {}

    def __init__(self, importer):
        self.importer = importer
        super().__init__()

    @staticmethod
    def create_additional_defaults(csv, row, defaults: dict = None):
        return defaults

    def import_product_type(self, csv, row, import_details: bool = False):
        sku = self.importer.get_product_sku(csv, row)
        if not sku:
            return None
        feature_set = self.importer.get_feature_set(csv, row, sku)
        report = {"product_type": self.product_type.name, "sku": sku}
        is_enabled = csv.get_row_value(row, COL_Enabled)
        kind_of_product = self.importer.get_kind_of_product(csv, row, sku)
        defaults = {}
        if kind_of_product:
            defaults["kind_of_product"] = kind_of_product

        if import_details and kind_of_product != "virtual":
            weight = csv.get_row_value_decimal(row, COL_Weight)
            width = csv.get_row_value_decimal(row, COL_Width)
            height = csv.get_row_value_decimal(row, COL_Height)
            deep = csv.get_row_value_decimal(row, COL_Deep)
            if weight is not None:
                defaults["weight"] = weight
            if width is not None:
                defaults["width"] = width
            if height is not None:
                defaults["height"] = height
            if deep is not None:
                defaults["deep"] = deep

        if self.importer.update_only:
            try:
                real_product = RealProduct.objects.get(sku=sku)
            except RealProduct.DoesNotExist:
                return None
        else:
            logger.info(f"sku: {sku}")
            real_product, created = RealProduct.objects.update_or_create(sku=sku, defaults=defaults)

        is_enabled = (
            True
            if is_enabled is None or is_enabled == "1" or is_enabled == 1 or is_enabled == True or is_enabled == "true"
            else False
        )
        defaults = {"feature_set": feature_set, "is_enabled": is_enabled}
        defaults = self.create_additional_defaults(csv, row, defaults)
        visibility_txt = csv.get_row_value(row, COL_Visibility)
        visibility = self.importer.establish_visibility(visibility_txt)
        if visibility is None and self.associated_skus_column is not None:
            configurable_sku = csv.get_row_value(row, self.associated_skus_column)
            if configurable_sku:
                visibility = ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY
            else:
                visibility = ProductVisibilityEnum.CATALOG_AND_SEARCH
        if visibility is None:
            visibility = ProductVisibilityEnum.UNKNOWN
        defaults["visibility"] = visibility
        try:
            product, created = self.model.objects.update_or_create(
                real_product=real_product, shop=self.importer.shop, defaults=defaults
            )
        except IntegrityError:
            raise Exception(
                f"Can not create {self.product_type.name}, probably already exist ProductSimple with same sku={sku}"
            )
        report["is_created"] = created
        self.importer.import_product_features(csv, row=row, product=product)
        self.importer.import_product_categories(csv, row=row, product=product)
        self.importer.import_product_pictures(csv, row=row, product=product, raport=report)
        return report, product

    def update_translations_only(self, csv, row):
        raise NotImplementedError("update_translations_only() requires self.importer.update_translations_only")

    def import_products_type_bulk(self, csv, rows):
        bev = ProductsBulkImportFromCsvEvent(file_path=self.importer.file_path, shop=self.importer.shop.idx)
        report_bulk = {
            "product_type": "Product Configurable",
            "skus": [],
            "exceptions": 0,
            "csv_rows_in_bulk": len(rows),
            "products_created": 0,
            "images_total_found": 0,
            "images_processed_ok": 0,
            "images_processed_error": 0,
            "images_unlinked": 0,
            "products_without_main_image": 0,
        }
        for row in rows:
            self.importer._threaded_cnt += 1
            self.importer.print_progress(self.importer._threaded_cnt, self.importer._threaded_total, self.name)
            try:
                if self.importer.update_translations_only:
                    report = self.update_translations_only(csv=csv, row=row)
                else:
                    report = self.import_product_type(csv=csv, row=row)
                if report is None:
                    continue
                report_bulk["skus"].append(report["sku"])
                if report["is_created"]:
                    report_bulk["products_created"] += 1
                if "images_total_found" in report:
                    report_bulk["images_total_found"] += report["images_total_found"]
                if "images_processed_ok" in report:
                    report_bulk["images_processed_ok"] += report["images_processed_ok"]
                if "images_processed_error" in report:
                    report_bulk["images_processed_error"] += report["images_processed_error"]
                if "images_unlinked" in report:
                    report_bulk["images_unlinked"] += report["images_unlinked"]
                if "is_main_image_found" in report and not report["is_main_image_found"]:
                    report_bulk["products_without_main_image"] += 1
                print(".", end="", flush=True)
            except Exception as e:
                report_bulk["exceptions"] += 1
                logger.error(f"Exception while importing row={row} e={e}")
                logger.exception(e)
                print("E", end="", flush=True)

        bev.set_details(report_bulk)
        bev.finish_with_success(finish_tag="Products bulk has been imported")
        return report_bulk
