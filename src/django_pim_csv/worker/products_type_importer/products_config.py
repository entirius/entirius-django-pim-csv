# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django_pim.models import (
    ConfigurableLink,
    FeatureTypeEnum,
    ProductClassEnum,
    ProductConfigurable,
    ProductSimple,
    RealProduct,
)
from idx_normalizator import normalize_idx

from django_pim_csv.csv.products import (
    COL_ConfigurableFeature,
    COL_ConfigurableSku,
)

from .products_base import ProductsImportBase

logger = logging.getLogger("django")


class ProductsConfigurableImporter(ProductsImportBase):
    associated_skus_column = COL_ConfigurableSku
    product_type = ProductClassEnum.ProductConfigurable
    name = "config"
    model = ProductConfigurable
    importer = None

    def update_translations_only(self, csv, row):
        if not self.importer.update_translations_only:
            raise Exception("update_translations_only_configurable() requires self.importer.update_translations_only")
        sku = self.importer.get_product_sku(csv, row)
        if not sku:
            return None
        try:
            real_product = RealProduct.objects.get(sku=sku)
        except RealProduct.DoesNotExist:
            return None
        product = ProductConfigurable.objects.filter(real_product=real_product, shop=self.importer.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Configurable", "sku": sku, "is_created": False}
        self.importer.import_product_features_t9n_only(csv, row=row, product=product)
        return report

    def import_product_subproducts_config(self, csv, row, configurable_product):
        config_features_idx_raw = csv.get_row_value(row, COL_ConfigurableFeature)
        if not config_features_idx_raw:
            if not self.importer.update_only:
                self.importer.error(
                    f"Configurable Product sku={configurable_product.sku} has not valid 'config features' set"
                )
            return
        config_features = []
        config_features_idx_raw = str(config_features_idx_raw)
        for feature_idx in config_features_idx_raw.split(","):
            feature_idx = normalize_idx(feature_idx)
            if not feature_idx:
                continue
            try:
                config_feature = self.importer.features_cache[feature_idx]
            except KeyError:
                raise Exception(f"Feature idx='{feature_idx}' does not exist")
            if config_feature.feature_type != FeatureTypeEnum.SELECT:
                self.importer.error(
                    f'Configurable feature idx="{config_feature.idx}" has invalid feature_type="{config_feature.feature_type_name}", must be SELECT'
                )
                return
            config_features.append(config_feature)
        if not config_features:
            self.importer.error(
                f"Configurable Product sku={configurable_product.sku} has not valid 'config features' set"
            )
            return
        subproducts_skus = self.importer.get_subproducts_skus(csv, row, COL_ConfigurableSku)
        if not subproducts_skus:
            if not self.importer.update_only:
                self.importer.error(
                    f"Configurable Product sku={configurable_product.sku} has no subproducts skus defined in csv col={COL_ConfigurableSku}"
                )
            return
        real_subproducts = RealProduct.objects.filter(sku__in=subproducts_skus)
        if len(real_subproducts) == 0:
            self.importer.error(
                f'Can not find subproducts for Configurable Product sku={configurable_product.sku} and subproducts_skus="{subproducts_skus}"'
            )
            return
        subproducts = (
            ProductSimple.objects.filter(real_product__in=real_subproducts, shop=self.importer.shop)
            .select_related("real_product")
            .prefetch_related("products_attributes", "products_attributes__feature")
        )

        subproducts_map = {sp.real_product.id: sp for sp in subproducts}

        # dobra, czyli mamy polaczyc ze soba ten zbior real_subproducts
        # uzywajac config_features
        cnt_linked_porducts = 0
        for real_subproduct in real_subproducts:
            subproduct = subproducts_map.get(real_subproduct.id)
            if subproduct is None:
                logger.error(
                    f'Can NOT link ConfigurableProduct="{configurable_product}" with SimpleProduct="{real_subproduct.sku}" '
                    f'because SimpleProduct does not exist in shop="{self.importer.shop.idx}", but RealProduct="{real_subproduct.sku}" does exist'
                )
                continue

            subproduct_attributes = [
                attr for attr in subproduct.products_attributes.all() if attr.feature in config_features
            ]

            for subproduct_attribute in subproduct_attributes:
                ConfigurableLink.objects.update_or_create(
                    product_configurable=configurable_product,
                    subproduct_attribute=subproduct_attribute,
                    defaults={"subproduct": subproduct},
                )
        logger.info(
            f"Configurable Product sku={configurable_product.sku} has been linked with {len(real_subproducts)} subproducts"
        )

    def import_product_type(self, csv, row, import_details: bool = False):
        report, product = super().import_product_type(csv, row, False)
        if product.is_enabled:
            self.import_product_subproducts_config(csv, row=row, configurable_product=product)
        return report

    def import_products_type_bulk(self, csv, rows):
        report_bulk = super().import_products_type_bulk(csv, rows)
        return report_bulk
