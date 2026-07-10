# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import concurrent.futures
import logging
import os
import re
from collections import Counter
from decimal import Decimal

import pytz
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.utils import IntegrityError
from django.utils import timezone
from django_pim.managers import FilesManager, PictureManager
from django_pim.models import (
    Attribute,
    BundleLink,
    BundleSection,
    ConfigurableLink,
    Feature,
    FeatureScopeEnum,
    FeatureSet,
    FeatureTypeEnum,
    FilesCategory,
    KindOfProductClass,
    KindOfProductEnum,
    PictureRoleEnum,
    Product,
    ProductAttribute,
    ProductBundle,
    ProductCategory,
    ProductClass,
    ProductClassEnum,
    ProductConfigurable,
    ProductCustom,
    ProductFile,
    ProductInCategory,
    ProductLink,
    ProductLinkTypeEnum,
    ProductPicture,
    ProductSimple,
    ProductVisibilityEnum,
    RealProduct,
    Shop,
    normalize_sku,
)
from idx_normalizator import normalize_idx, validate_idx

from django_pim_csv.worker.products_type_importer import (
    ProductsBundleImporter,
    ProductsConfigurableImporter,
    ProductsCustomImporter,
    ProductsSimpleImporter,
)
from django_pim_csv.worker.products_type_importer.products_base import ProductsImportBase

from ..bi import ProductsImportFromCsvEndEvent, ProductsImportFromCsvStartEvent
from ..csv.products import (
    COL_SKU,
    COL_BundleSectionIdx,
    COL_BundleSku,
    COL_Category,
    COL_ConfigurableFeature,
    COL_ConfigurableSku,
    COL_Deep,
    COL_Enabled,
    COL_FeatureSet,
    COL_FeatureSetCustom,
    COL_Files,
    COL_FilesCategory,
    COL_FilesLabel,
    COL_Height,
    COL_Images,
    COL_Img_General_1,
    COL_Img_General_2,
    COL_ImgMain,
    COL_KindOfProduct,
    COL_Link_CrossSell,
    COL_Link_Navigation,
    COL_Link_Related,
    COL_Link_Unknown,
    COL_Link_UpSell,
    COL_ProductType,
    COL_Visibility,
    COL_Weight,
    COL_Width,
    ProductsCsv,
)
from ..settings import (
    ALLOW_CHANGE_PRODUCT_TYPE,
    BUNDLE_SKU_QUANTITY_SEPARATOR,
    CSV_IMPORT_PRODUCTS_BULK_SIZE,
    CSV_IMPORT_PRODUCTS_MAX_WORKERS,
    IMPORT_PRODUCTS_PIM_CSV_SKIP_FEATURES_INFO,
    SKU_LINK_SEPARATOR,
    T9N_DEFAULT_LANG,
)
from .abstract import AbstractSync

COL_ImportStatus = "import status"
COL_ImportMessage = "import message"

logger = logging.getLogger("django")


#
# converting strings like:
#   "14 000,45"
#   "39.000000"
#   "129"
#   "17,5"
# to Decimal (yes, it is Magento)
#
def price_to_decimal(price_str, places=2):
    if price_str is None:
        return None
    if isinstance(price_str, str):
        price_str = price_str.replace(" ", "")
        if price_str.find(".") >= 0:
            if price_str.find(",") >= 0:
                raise Exception('Price="%s" contains "." and ","' % price_str)
        else:
            price_str = price_str.replace(",", ".")
        price_str = price_str.strip()
        if price_str == "":
            return None
    places = places * -1
    quantize = Decimal(10) ** places  # same as Decimal('0.01')
    return Decimal(price_str).quantize(quantize)


class ProductsImporter(AbstractSync):
    def __init__(self, file_path: str, shop_id: int | None = None, shop_idx: str | None = None):
        super().__init__()
        """
        shop_idx_path jest to identyfikator sklepu w formacie: 'BusinessUnit.idx'.'Shop.idx' ex: 'acme.shop_idx'
        """
        params_quantity = len({id(shop_id), id(shop_idx)} - {id(None)})
        if params_quantity != 1:
            raise ValueError("Exactly one of: shop_id or shop_idx_path must be set")
        if shop_id is not None:
            self.shop = Shop.objects.prefetch_related("languages").get(id=shop_id)
        elif shop_idx is not None:
            self.shop = Shop.objects.prefetch_related("languages").get(idx=shop_idx)
        else:
            raise Exception("should not happened")
        self.file_path = file_path
        self.shop_languages = list(self.shop.languages.all().order_by("iso2"))
        self.feature_sets_cache = {}
        self.features_cache = {}
        self.products_cache = {}
        self.default_feature_set = None
        self._attributes_cache = {}
        self._product_categories_cache = {}
        self.init_feature_sets()
        self.init_features_cache()
        self.init_products_cache()
        self.init_system_features_cache()
        self._feature_set_importable_features_cache = {}
        self._threaded_cnt = None
        self._threaded_total = None

    def init_feature_sets(self):
        print("Building existing Features Sets cache ... ", end="", flush=True)
        self.feature_sets_cache = {}
        for feature_set in FeatureSet.objects.prefetch_related("features").all():
            self.feature_sets_cache[feature_set.idx] = feature_set
            if feature_set.is_default:
                self.default_feature_set = feature_set
        print("done")

    def init_features_cache(self):
        print("Building existing Features cache ... ", end="", flush=True)
        self.features_cache = {}
        for feature in Feature.objects.all():
            self.features_cache[feature.idx] = feature
        print("done")

    def init_products_cache(self):
        print("Building existing Products cache ... ", end="", flush=True)
        self.products_cache = {}
        for product in Product.objects.filter(shop=self.shop).select_related("real_product"):
            self.products_cache[product.real_product.sku] = product
        print("done")

    def init_system_features_cache(self):
        print("Building system features cache ... ", end="", flush=True)
        self.system_features = list(Feature.objects.filter(scope=FeatureScopeEnum.SYSTEM).order_by("display_order"))
        self.system_features_t9n = list(
            Feature.objects.filter(
                scope=FeatureScopeEnum.SYSTEM,
                feature_type__in=[FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N, FeatureTypeEnum.JSON_T9N],
            ).order_by("display_order")
        )
        print("done")

    def is_feature_importable(self, csv, feature):
        """
        True jeśli istnieje jakaś powiadana kolumna w pliku csv
        """
        csv_col_exists = False

        if feature.feature_type in (
            FeatureTypeEnum.VARCHAR255,
            FeatureTypeEnum.TEXT,
            FeatureTypeEnum.SELECT,
            FeatureTypeEnum.MULTISELECT,
            FeatureTypeEnum.BOOL,
            FeatureTypeEnum.DECIMAL,
            FeatureTypeEnum.JSON,
            FeatureTypeEnum.DATETIME,
        ):
            col_idx = self.generate_feature_col_idx(feature.idx)
            if csv.get_col_index(col_idx):
                csv_col_exists = True

        elif feature.feature_type in (
            FeatureTypeEnum.VARCHAR255_T9N,
            FeatureTypeEnum.TEXT_T9N,
            FeatureTypeEnum.JSON_T9N,
        ):
            for lang in self.shop_languages:
                col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                if csv.get_col_index(col_idx):
                    csv_col_exists = True
                    break

        elif feature.feature_type in (FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS):
            col_idx = self.generate_feature_col_idx(feature.idx)
            if csv.get_col_index(col_idx):
                csv_col_exists = True
            else:
                for lang in self.shop_languages:
                    col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                    if csv.get_col_index(col_idx):
                        csv_col_exists = True
                        break
        else:
            self.error(f"Import of Feature type={feature.feature_type_name} is not supported for idx={feature.idx}")
        return csv_col_exists

    def get_feature_set_importable_features(self, csv, feature_set):
        """
        Zwraca listę features: najpierw systemowe potem dowiązane do feature setu
        Ale tylko te, które mogą być zaimportowane w danym CSV, czyli istnieją odpowiadające im kolumny
        :param feature_set:
        :return:
        """

        if feature_set in self._feature_set_importable_features_cache:
            return self._feature_set_importable_features_cache[feature_set]
        features = []
        # Use cached system features
        for feature in self.system_features:
            if self.is_feature_importable(csv, feature):
                features.append(feature)
        for feature in feature_set.features.all().order_by("display_order"):
            if self.is_feature_importable(csv, feature):
                features.append(feature)
        self._feature_set_importable_features_cache[feature_set] = features
        return features

    def establish_visibility(self, visibility_txt):
        if visibility_txt is None:
            return None
        visibility_txt = str(visibility_txt).strip().lower()
        if visibility_txt == "":
            return None
        m = {
            "not visible individualy": ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY,
            "not visible individually": ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY,
            "catalog": ProductVisibilityEnum.CATALOG,
            "search": ProductVisibilityEnum.SEARCH,
            "catalog, search": ProductVisibilityEnum.CATALOG_AND_SEARCH,
            "catalog and search": ProductVisibilityEnum.CATALOG_AND_SEARCH,
        }
        if visibility_txt in m:
            return m[visibility_txt]
        logger.warning(f"Invalid product visibility={visibility_txt}")
        return None

    def import_feature_bool(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value_bool(row, col_idx)
        if value is None:
            exists = False
        else:
            exists = True
        if feature.is_required and not exists and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        if exists:
            product_attr, created = ProductAttribute.objects.update_or_create(
                product=product, feature=feature, defaults={"value_bool": value}
            )
        elif not exists and not self.update_only and self.delete_attr:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

    def import_feature_datetime(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value_datetime(row, col_idx)
        if value is None:
            exists = False
        else:
            exists = True
        if feature.is_required and not exists and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        if exists:
            product_attr, created = ProductAttribute.objects.update_or_create(
                product=product, feature=feature, defaults={"value_datetime": value}
            )
        elif not exists and not self.update_only:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

    def import_feature_decimal(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value_decimal(row, col_idx)
        if value is None:
            exists = False
        else:
            exists = True
        if feature.is_required and not exists and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        if exists:
            product_attr, created = ProductAttribute.objects.update_or_create(
                product=product, feature=feature, defaults={"value_decimal": value}
            )
        elif not exists and not self.update_only and self.delete_attr:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

    def import_feature_metric(self, csv, row, product, feature):
        value_list = []
        for lang in self.shop_languages:
            col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
            value = csv.get_row_value_decimal(row, col_idx)
            if value not in (None, "", []):
                value_list.append(value)

        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value_decimal(row, col_idx)
        if value not in (None, "", []):
            value_list.append(value)

        counts = Counter(value_list)
        value = counts.most_common(1)
        if value:
            value = value[0][0]

        if value is None:
            exists = False
        else:
            exists = True

        if value not in (None, "", []):
            product_attr, created = ProductAttribute.objects.update_or_create(
                product=product, feature=feature, defaults={"value_decimal": value}
            )
        elif not exists and not self.update_only:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

        if feature.is_required and not value and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")

    def import_feature_json(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        try:
            value = csv.get_row_value_json(row, col_idx)
        except Exception:
            self.error(f"There is invalid JSON value in col_idx={col_idx}, feature={feature.idx}, row={row}")
            return
        if value is None:
            exists = False
        else:
            exists = True
        if feature.is_required and not exists and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        if exists:
            product_attr, created = ProductAttribute.objects.update_or_create(
                product=product, feature=feature, defaults={"value_json": value}
            )
        elif not exists and not self.update_only and self.delete_attr:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

    def import_feature_json_t9n(self, csv, row, product, feature):
        def compose_value_t9n():
            value_t9n = {}
            for lang in self.shop_languages:
                col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                try:
                    value = csv.get_row_value_json(row, col_idx)
                except Exception:
                    self.error(f"There is invalid JSON value in col_idx={col_idx}, feature={feature.idx}, row={row}")
                    return None
                if value:
                    value_t9n[lang.iso2] = value
            return value_t9n

        def update_value_t9n(value_t9n):
            is_updated = False
            for lang in self.shop_languages:
                col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                try:
                    value = csv.get_row_value_json(row, col_idx)
                except Exception:
                    self.error(f"There is invalid JSON value in col_idx={col_idx}, feature={feature.idx}, row={row}")
                    return False

                if value is not None:
                    if not value_t9n.get(lang.iso2, None) or value != value_t9n[lang.iso2]:
                        value_t9n[lang.iso2] = value
                        is_updated = True
            return is_updated

        if self.update_only:
            # Use prefetched attributes if available
            if hasattr(product, "_prefetched_attributes_by_feature"):
                product_attribute = product._prefetched_attributes_by_feature.get(feature.id)
            else:
                product_attribute = ProductAttribute.objects.filter(product=product, feature=feature).first()
            if product_attribute is None:
                # create
                value_t9n = compose_value_t9n()
                if value_t9n is not None:
                    product_attribute = ProductAttribute(product=product, feature=feature, value_json=value_t9n)
                    product_attribute.save()
            else:
                # update
                is_updated = update_value_t9n(product_attribute.value_json)
                if is_updated:
                    product_attribute.save()
        else:
            value_t9n = compose_value_t9n()

            if value_t9n:
                ProductAttribute.objects.update_or_create(
                    product=product, feature=feature, defaults={"value_json": value_t9n}
                )
            elif not self.update_only and self.delete_attr:
                delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()
                if feature.is_required:
                    self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")

    def import_feature_text_t9n(self, csv, row, product, feature):
        def compose_value_t9n():
            value_t9n = {}
            obj_exists = False
            for lang in self.shop_languages:
                col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                value = csv.get_row_value(row, col_idx)
                exists = self.does_text_value_exist(value)
                if exists:
                    obj_exists = True
                if value:
                    value_t9n[lang.iso2] = str(value).strip()
            if not obj_exists:
                value_t9n = None
            return value_t9n

        def update_value_t9n(value_t9n):
            is_updated = False
            for lang in self.shop_languages:
                col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
                value = csv.get_row_value(row, col_idx)
                exists = self.does_text_value_exist(value)
                if exists:
                    value = str(value).strip()
                    if not value_t9n.get(lang.iso2, None) or value != value_t9n[lang.iso2]:
                        value_t9n[lang.iso2] = value
                        is_updated = True
            return is_updated

        def is_value_t9n_empty(value_t9n):
            for lang, val in value_t9n.items():
                if val:
                    return False
            return True

        # Zawsze stara sie nie usuwac istniejacych wpisow w innych lang
        # Usuwane jest wpis tylko wtedy gdy w csv wszystkie jezyki sa puste
        if hasattr(product, "_prefetched_attributes_by_feature"):
            product_attribute = product._prefetched_attributes_by_feature.get(feature.id)
        else:
            product_attribute = ProductAttribute.objects.filter(product=product, feature=feature).first()
        value_t9n = compose_value_t9n()

        if product_attribute is None:
            # create
            if value_t9n is not None:
                product_attribute = ProductAttribute(product=product, feature=feature, value_txt_t9n=value_t9n)
                product_attribute.save()
            else:
                if feature.is_required:
                    self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        else:
            if value_t9n is None and not self.update_only and self.delete_attr:
                product_attribute.delete()
                return

            if value_t9n is None:
                return

            value_in_db = product_attribute.value_txt_t9n if product_attribute.value_txt_t9n else {}
            if isinstance(value_in_db, dict) and value_t9n:
                value_in_db.update(value_t9n)

            if value_t9n is None and not self.update_only and self.delete_attr:
                product_attribute.delete()
            else:
                product_attribute.value_txt_t9n = value_in_db
                product_attribute.save()

    def does_text_value_exist(self, value):
        if value is None:
            return False
        value = str(value)
        value.strip()
        if not value:
            return False
        return True

    def import_feature_text(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value(row, col_idx)
        exists = self.does_text_value_exist(value)
        if exists:
            value = str(value)
            ProductAttribute.objects.update_or_create(product=product, feature=feature, defaults={"value_txt": value})
        else:
            if feature.is_required:
                self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
            if not exists and not self.update_only and self.delete_attr:
                delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()

    def get_attribute_by_idx(self, feature, attribute_idx):
        try:
            if attribute_idx == "" or attribute_idx is None or attribute_idx == "None":
                if not feature.is_required:
                    return

            attribute_idx = str(attribute_idx).strip()
            validate_idx(attribute_idx, min_len=1, max_len=128)
        except ValueError:
            self.error(f'Feature={feature.idx} Attribute idx not valid: "{attribute_idx}"')
            return None

        cache_key = (feature.id, attribute_idx)
        if cache_key in self._attributes_cache:
            return self._attributes_cache[cache_key]

        attribute, created = Attribute.objects.get_or_create(
            feature=feature, idx=attribute_idx, defaults={"name_t9n": {}}
        )

        self._attributes_cache[cache_key] = attribute
        return attribute

    def get_attribute_by_name(self, feature, value_name, lang, allow_add_new=False):
        attribute_idx = Attribute.normalize_idx(value_name)

        cache_key = (feature.id, attribute_idx)
        if cache_key in self._attributes_cache:
            return self._attributes_cache[cache_key]

        if allow_add_new:
            name_t9n = {}
            name_t9n[lang] = value_name
            attribute, created = Attribute.objects.get_or_create(
                feature=feature, idx=attribute_idx, defaults={"name_t9n": name_t9n}
            )
        else:
            try:
                attribute = Attribute.objects.get(feature=feature, idx=attribute_idx)
            except:
                self.error(f'Can not get attribute={attribute_idx} for feature="{feature.idx}"')
                return None

        self._attributes_cache[cache_key] = attribute
        return attribute

    def import_feature_select(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        value = csv.get_row_value(row, col_idx)

        if value is None and not self.update_only and self.delete_attr:
            delprod, _ = ProductAttribute.objects.filter(product=product, feature=feature).delete()
            return None
        if value is None:
            return None

        if feature.is_required and value is None:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")

        attribute = self.get_attribute_by_idx(feature=feature, attribute_idx=value)
        if attribute is None:
            if feature.is_required:
                self.error(f"Can not find attribute for required feature idx={feature.idx}, value={value}")
            return None
        ProductAttribute.objects.update_or_create(product=product, feature=feature, defaults={"attribute": attribute})

    def import_feature_multiselect(self, csv, row, product, feature):
        col_idx = self.generate_feature_col_idx(feature.idx)
        values = csv.get_row_value(row, col_idx)
        if feature.is_required and values is None and not self.update_only:
            self.error(f"Product sku={product.real_product.sku} required feature is empty idx={feature.idx}")
        if values is None and not self.update_only and self.delete_attr:
            delfeature, _ = (ProductAttribute.objects.filter(product=product, feature=feature)).delete()
            return None
        separator = ","
        values = str(values).split(separator)
        prod_features_linked = []
        cnt_created = 0
        for value in values:
            try:
                attribute = self.get_attribute_by_idx(feature=feature, attribute_idx=value)
            except Exception as e:
                self.error(f'Exception while geting attribute: feature="{feature}" value="{value}" exception={e}')
                continue
            if attribute is None:
                if feature.is_required:
                    self.error(f"Can not find attribute for required feature idx={feature.idx}, value={value}")
                continue
            prod_attr, created = ProductAttribute.objects.get_or_create(
                product=product, feature=feature, attribute=attribute
            )
            if created:
                cnt_created += 1
            prod_features_linked.append(prod_attr.id)
        if not self.update_only and self.delete_attr:
            delfeature, _ = (
                ProductAttribute.objects.filter(product=product, feature=feature)
                .exclude(pk__in=prod_features_linked)
                .delete()
            )
            logger.info(
                f"Product {product} features: linked={len(prod_features_linked)} created={cnt_created} detached={delfeature}"
            )

    def import_product_feature(self, feature, csv, row, product):
        if feature.feature_type in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N):
            self.import_feature_text_t9n(csv, row, product, feature)
        elif feature.feature_type in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
            self.import_feature_text(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.SELECT:
            self.import_feature_select(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.MULTISELECT:
            self.import_feature_multiselect(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.BOOL:
            self.import_feature_bool(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.DECIMAL:
            self.import_feature_decimal(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.JSON:
            self.import_feature_json(csv, row, product, feature)
        elif feature.feature_type in (FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS):
            self.import_feature_metric(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.JSON_T9N:
            self.import_feature_json_t9n(csv, row, product, feature)
        elif feature.feature_type == FeatureTypeEnum.DATETIME:
            self.import_feature_datetime(csv, row, product, feature)
        else:
            self.error(f"Import of Feature type={feature.feature_type_name} is not supported for idx={feature.idx}")

    def import_product_features(self, csv, row, product):
        # Prefetch all ProductAttributes for this product to avoid massive N+1 queries
        # This reduces queries from N*M (where N=features, M=products) to just 1 per product
        existing_attrs_by_feature = {
            pa.feature_id: pa
            for pa in ProductAttribute.objects.filter(product=product).select_related("feature", "attribute")
        }
        product._prefetched_attributes_by_feature = existing_attrs_by_feature

        features = self.get_feature_set_importable_features(csv, product.feature_set)
        for feature in features:
            self.import_product_feature(feature, csv, row, product)

        if hasattr(product, "_prefetched_attributes_by_feature"):
            delattr(product, "_prefetched_attributes_by_feature")

        # Zolv: tutaj przyspieszyc
        # for feature in Feature.objects.filter(scope=FeatureScopeEnum.SYSTEM).order_by("display_order"):
        #     self.import_product_feature(feature, csv, row, product)
        # for feature in product.feature_set.features.all().order_by("display_order"):
        #     self.import_product_feature(feature, csv, row, product)

    def import_product_features_t9n_only(self, csv, row, product):
        # Prefetch all ProductAttributes for this product to avoid N+1 queries
        existing_attrs_by_feature = {
            pa.feature_id: pa
            for pa in ProductAttribute.objects.filter(product=product).select_related("feature", "attribute")
        }
        product._prefetched_attributes_by_feature = existing_attrs_by_feature

        for feature in self.system_features_t9n:
            self.import_product_feature(feature, csv, row, product)
        for feature in product.feature_set.features.filter(
            feature_type__in=[FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N, FeatureTypeEnum.JSON_T9N]
        ).order_by("display_order"):
            self.import_product_feature(feature, csv, row, product)

        # Clean up
        if hasattr(product, "_prefetched_attributes_by_feature"):
            delattr(product, "_prefetched_attributes_by_feature")

    def import_product_pictures(self, csv, row, product, raport):
        raport["images_total_found"] = 0
        raport["images_processed_ok"] = 0
        raport["images_processed_error"] = 0
        raport["images_unlinked"] = 0
        raport["is_main_image_found"] = False
        if not csv.exists_col(COL_ImgMain):
            return
        separator = ","
        if self.skip_pictures:
            return

        existing_pics = {
            pp.position: pp for pp in ProductPicture.objects.filter(product=product).select_related("picture")
        }

        paths = []
        for path in [
            csv.get_row_value(row, COL_ImgMain),
            csv.get_row_value(row, COL_Img_General_1),
            csv.get_row_value(row, COL_Img_General_2),
        ]:
            if path:
                paths.append(path)
        images_values = csv.get_row_value(row, COL_Images)
        if images_values:
            for img_value in images_values.split(separator):
                img_value = img_value.strip()
                if img_value:
                    paths.append(img_value)
        validate = URLValidator()
        is_main_image_found = False
        is_general_image_found = 0
        raport["images_total_found"] = len(paths)
        prodpics_linked = []
        position = 1
        for path in paths:
            if not path:
                continue
            path = path.strip()
            if path[:7] == "http://" or path[:8] == "https://" or path[:6] == "ftp://":
                url = path
                try:
                    validate(url)
                except ValidationError:
                    logger.warning(f"Ignoring invalid picture url: {url}")
                    raport["images_processed_error"] += 1
                    continue
                picture, is_downloaded = PictureManager.download_picture(url)
            else:
                if path[0] == "/":
                    full_path = path
                else:
                    full_path = os.path.join(os.path.dirname(self.file_path), path)
                if not os.path.exists(full_path):
                    logger.error(f'Can not import not existing picture path="{full_path}"')
                    raport["images_processed_error"] += 1
                    continue
                try:
                    # tutaj nastepuje validacja, nalezy kontynuowac przy nieprawidlowych zdjeciach
                    picture = PictureManager.get_picture(full_path)
                except Exception as e:
                    logger.error(f"Error while loading picture path={path}, e={e}")
                    raport["images_processed_error"] += 1
                    continue
            try:
                if is_main_image_found:
                    if is_general_image_found == 2:
                        picture_role = PictureRoleEnum.ANGLE
                    else:
                        picture_role = PictureRoleEnum.GENERAL
                        is_general_image_found += 1
                else:
                    picture_role = PictureRoleEnum.MAIN
                    is_main_image_found = True

                if position in existing_pics:
                    productpic = existing_pics[position]
                    productpic.picture = picture
                    productpic.picture_role = picture_role
                    productpic.save()
                    created = False
                else:
                    productpic = ProductPicture.objects.create(
                        product=product, position=position, picture=picture, picture_role=picture_role
                    )
                    created = True

                prodpics_linked.append(productpic.pk)
                position += 1
            except Exception as e:
                logger.error(f"Error while importing picture path={path}, e={e}")
                raport["images_processed_error"] += 1
                continue
            raport["images_processed_ok"] += 1
        raport["is_main_image_found"] = is_main_image_found
        delprodpic = 0
        if raport["images_processed_error"] == 0:
            delprodpic, _ = ProductPicture.objects.filter(product=product).exclude(pk__in=prodpics_linked).delete()
        else:
            logger.info(f"Product {product} pictures unlinking is skipped due to pictures errors")
        raport["images_unlinked"] = delprodpic
        logger.info(f"Product {product} pictures: linked={len(prodpics_linked)} detached={delprodpic}")
        if not is_main_image_found:
            logger.error(f"Product sku={product.sku} is missing main picture")

    def import_product_files(self, csv, row, product):
        separator = ","
        if self.skip_files:
            return
        paths_file = []
        all_file_category = []
        all_file_label = []
        files_values = csv.get_row_value(row, COL_Files)
        category_files_values = csv.get_row_value(row, COL_FilesCategory)
        files_label = csv.get_row_value(row, COL_FilesLabel)

        if files_values:
            for file_value in files_values.split(separator):
                file_value = file_value.strip()
                if file_value:
                    paths_file.append(file_value)

        if category_files_values:
            for file_category_value in category_files_values.split(separator):
                file_category_value = file_category_value.strip()
                if file_category_value:
                    all_file_category.append(file_category_value)

        if files_label:
            for file_label in files_label.split(separator):
                file_label = file_label.strip()
                if file_label:
                    all_file_label.append(file_label)

        validate = URLValidator()
        for idx, path in enumerate(paths_file):
            file_label = all_file_label[idx] if len(all_file_category) > 0 else None
            if not path:
                continue
            path = path.strip()
            # download file
            if path[:7] == "http://" or path[:8] == "https://" or path[:6] == "ftp://":
                url = path
                try:
                    validate(url)
                except ValidationError:
                    logger.warning(f"Ignoring invalid file url: {url}")
                    continue
                file, is_downloaded = FilesManager.download_file(file_path=url, file_label=file_label)
                file_name = path.split("/")[-1]

            # get file from directory
            else:
                if path[0] == "/":
                    full_path = path
                else:
                    full_path = os.path.join(os.path.dirname(self.file_path), path)
                if not os.path.exists(full_path):
                    logger.error(f'Can not import not existing picture path="{full_path}"')
                    continue
                file_name = os.path.basename(full_path)
                file = FilesManager.get_file(file_path=full_path, file_label=file_label, original_file_name=file_name)

            try:
                productpic, created = ProductFile.objects.update_or_create(file=file, product=product)
            except Exception as e:
                logger.error(f"Error while importing file path={path}, e={e}")

            code_category = all_file_category[idx] if len(all_file_category) > 0 else None
            try:
                if code_category not in [None, ""]:
                    product_cat_file, created = FilesCategory.objects.update_or_create(code=code_category)
            except Exception as e:
                logger.error(f"Error while importing category file path={path}, e={e}")

                continue

            file.file_category = product_cat_file
            file.save()

    def delete_unpined_category_links(self, cids_linked, product, cnt_created):
        delcategory, _ = ProductInCategory.objects.filter(product=product).exclude(id__in=cids_linked).delete()
        logger.info(
            f"Product {product} categories: linked={len(cids_linked)} created={cnt_created} detached={delcategory}"
        )

    def import_product_categories(self, csv, row, product):
        if not csv.exists_col(COL_Category):
            return
        value_raw = csv.get_row_value(row, COL_Category)

        cids_linked = []
        cnt_created = 0

        if value_raw is None:
            self.delete_unpined_category_links(cids_linked, product, cnt_created)
            logger.info(f'Product sku={product.sku} has not "category" set')
            return
        value_raw = str(value_raw).strip()
        values = re.split("[,;]", value_raw)

        # Prefetch existing ProductInCategory to avoid N+1 queries
        existing_product_in_categories = {
            pic.category_id: pic for pic in ProductInCategory.objects.filter(product=product).select_related("category")
        }

        cids_linked = []
        cnt_created = 0
        for category_idx in values:
            category_idx = ProductCategory.normalize_idx(category_idx)
            if not category_idx:
                continue

            cache_key = (self.shop.id, category_idx)
            if cache_key in self._product_categories_cache:
                category = self._product_categories_cache[cache_key]
            else:
                category, created = ProductCategory.objects.get_or_create(
                    shop=self.shop,
                    idx=category_idx,
                    defaults={"name_t9n": {T9N_DEFAULT_LANG: category_idx}, "is_active": False, "is_in_menu": False},
                )
                self._product_categories_cache[cache_key] = category

            if category.id in existing_product_in_categories:
                product_in_category = existing_product_in_categories[category.id]
                created = False
            else:
                product_in_category = ProductInCategory.objects.create(product=product, category=category, position=0)
                created = True

            if created:
                cnt_created += 1
            cids_linked.append(product_in_category.id)
        self.delete_unpined_category_links(cids_linked, product, cnt_created)

    def get_feature_set(self, csv, row, sku):
        if csv.exists_col(COL_FeatureSet):
            feature_set_idx = csv.get_row_value(row, COL_FeatureSet)
            if feature_set_idx:
                try:
                    feature_set = self.feature_sets_cache[feature_set_idx]
                    return feature_set
                except KeyError:
                    raise Exception(f"FeatureSet idx='{feature_set_idx}' does not exist, sku={sku}")
        if self.default_feature_set is not None:
            return self.default_feature_set
        raise Exception(f"Can not discover FeatureSet for sku={sku}")

    def get_feature_set_for_customization(self, csv, row, sku):
        if csv.exists_col(COL_FeatureSetCustom):
            feature_set_idx = csv.get_row_value(row, COL_FeatureSet)
            if feature_set_idx:
                try:
                    feature_set = self.feature_sets_cache[feature_set_idx]
                    return feature_set
                except KeyError:
                    raise Exception(f"FeatureSet idx='{feature_set_idx}' does not exist, sku={sku}")
        if self.default_feature_set is not None:
            return self.default_feature_set
        raise Exception(f"Can not discover FeatureSet for sku={sku}")

    def import_product_simple(self, csv, row):
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        feature_set = self.get_feature_set(csv, row, sku)
        report = {"product_type": "Product Simple", "sku": sku}
        weight = csv.get_row_value_decimal(row, COL_Weight)
        width = csv.get_row_value_decimal(row, COL_Width)
        height = csv.get_row_value_decimal(row, COL_Height)
        deep = csv.get_row_value_decimal(row, COL_Deep)
        defaults = {}
        if weight is not None:
            defaults["weight"] = weight
        if width is not None:
            defaults["width"] = width
        if height is not None:
            defaults["height"] = height
        if deep is not None:
            defaults["deep"] = deep
        if self.update_only:
            try:
                real_product = RealProduct.objects.get(sku=sku)
            except RealProduct.DoesNotExist:
                return None
        else:
            logger.info(f"sku: {sku}")
            real_product, created = RealProduct.objects.update_or_create(sku=sku, defaults=defaults)

        is_enabled = csv.get_row_value(row, COL_Enabled)
        is_enabled = (
            True
            if is_enabled is None or is_enabled == "1" or is_enabled == 1 or is_enabled == True or is_enabled == "true"
            else False
        )

        defaults = {"feature_set": feature_set, "is_enabled": is_enabled}
        visibility_txt = csv.get_row_value(row, COL_Visibility)
        visibility = self.establish_visibility(visibility_txt)
        if visibility is None:
            configurable_sku = csv.get_row_value(row, COL_ConfigurableSku)
            if configurable_sku:
                visibility = ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY
            else:
                visibility = ProductVisibilityEnum.CATALOG_AND_SEARCH
        defaults["visibility"] = visibility
        product, created = ProductSimple.objects.update_or_create(
            real_product=real_product, shop=self.shop, defaults=defaults
        )
        report["is_created"] = created
        self.import_product_features(csv, row=row, product=product)
        self.import_product_categories(csv, row=row, product=product)
        self.import_product_pictures(csv, row=row, product=product, raport=report)
        self.import_product_files(csv, row=row, product=product)
        return report

    def update_translations_only_product_simple(self, csv, row):
        if not self.update_translations_only:
            raise Exception("update_translations_only_product_simple() requires self.update_translations_only")
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        try:
            real_product = RealProduct.objects.get(sku=sku)
        except RealProduct.DoesNotExist:
            return None
        product = ProductSimple.objects.filter(real_product=real_product, shop=self.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Simple", "sku": sku, "is_created": False}
        self.import_product_features_t9n_only(csv, row=row, product=product)
        return report

    # self.import_product_configurable_sku(csv, sku, row=row, product=product)
    # def import_product_configurable_sku(self, csv, sku, row, product):
    #     value = csv.get_row_value(row, COL_ConfigurableSku)
    #     if value is None:
    #         return
    #     value = str(value).strip().lower()
    #     if not value:
    #         return
    #     if value not in self.configurable_sku_map:
    #         self.configurable_sku_map[value] = []
    #     self.configurable_sku_map[value].append(sku)

    def get_subproducts_skus(self, csv, row, col):
        subproducts_skus = []
        skus_raw = csv.get_row_value(row, col)
        if not skus_raw:
            return []
        for sku_raw in str(skus_raw).split(","):
            sku = normalize_sku(sku_raw)
            if sku:
                subproducts_skus.append(sku)
        return subproducts_skus

    def get_subproducts_skus_bundle(self, csv, row, col) -> dict:
        # return {"unit-sku-1": 2, "unit-sku-2": 1}
        subproducts_skus = {}
        skus_raw = csv.get_row_value(row, col)
        if not skus_raw:
            return {}
        for sku_raw in str(skus_raw).split(","):
            try:
                subproduct_data = str(sku_raw).split(BUNDLE_SKU_QUANTITY_SEPARATOR)
                sku = normalize_sku(subproduct_data[0])
                if sku:
                    subproducts_skus[sku] = subproduct_data[1]
            except IndexError:
                continue
        return subproducts_skus

    def import_product_subproducts_config(self, csv, row, configurable_product):
        config_features_idx_raw = csv.get_row_value(row, COL_ConfigurableFeature)
        if not config_features_idx_raw:
            if not self.update_only:
                self.error(f"Configurable Product sku={configurable_product.sku} has not valid 'config features' set")
            return
        config_features = []
        config_features_idx_raw = str(config_features_idx_raw)
        for feature_idx in config_features_idx_raw.split(","):
            feature_idx = normalize_idx(feature_idx)
            if not feature_idx:
                continue
            try:
                config_feature = self.features_cache[feature_idx]
            except KeyError:
                raise Exception(f"Feature idx='{feature_idx}' does not exist")
            if config_feature.feature_type != FeatureTypeEnum.SELECT:
                self.error(
                    f'Configurable feature idx="{config_feature.idx}" has invalid feature_type="{config_feature.feature_type_name}", must be SELECT'
                )
                return
            config_features.append(config_feature)
        if not config_features:
            self.error(f"Configurable Product sku={configurable_product.sku} has not valid 'config features' set")
            return
        subproducts_skus = self.get_subproducts_skus(csv, row, COL_ConfigurableSku)
        if not subproducts_skus:
            if not self.update_only:
                self.error(
                    f"Configurable Product sku={configurable_product.sku} has no subproducts skus defined in csv col={COL_ConfigurableSku}"
                )
            return
        real_subproducts = RealProduct.objects.filter(sku__in=subproducts_skus)
        if len(real_subproducts) == 0:
            self.error(
                f'Can not find subproducts for Configurable Product sku={configurable_product.sku} and subproducts_skus="{subproducts_skus}"'
            )
            return
        # dobra, czyli mamy polaczyc ze soba ten zbior real_subproducts
        # uzywajac config_features
        cnt_linked_porducts = 0
        for real_subproduct in real_subproducts:
            try:
                subproduct = ProductSimple.objects.get(real_product=real_subproduct, shop=self.shop)
            except ProductSimple.DoesNotExist:
                logger.error(
                    f'Can NOT link ConfigurableProduct="{configurable_product}" with SimpleProduct="{real_subproduct.sku}" '
                    f'because SimpleProduct does not exist in shop="{self.shop.idx}", but RealProduct="{real_subproduct.sku}" does exist'
                )
                continue
            subproduct_attributes = subproduct.products_attributes.filter(feature__in=config_features)
            for subproduct_attribute in subproduct_attributes:
                ConfigurableLink.objects.update_or_create(
                    product_configurable=configurable_product,
                    subproduct_attribute=subproduct_attribute,
                    defaults={"subproduct": subproduct},
                )
        logger.info(
            f"Configurable Product sku={configurable_product.sku} has been linked with {len(real_subproducts)} subproducts"
        )

    def import_product_configurable(self, csv, row):
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        feature_set = self.get_feature_set(csv, row, sku)
        report = {"product_type": "Product Configurable", "sku": sku}
        if self.update_only:
            try:
                real_product = RealProduct.objects.get(sku=sku)
            except RealProduct.DoesNotExist:
                return None
        else:
            logger.info(f"sku: {sku}")
            real_product, created = RealProduct.objects.update_or_create(sku=sku, defaults={})
        is_enabled = csv.get_row_value(row, COL_Enabled)

        is_enabled = (
            True
            if is_enabled is None or is_enabled == "1" or is_enabled == 1 or is_enabled == True or is_enabled == "true"
            else False
        )
        defaults = {"feature_set": feature_set, "is_enabled": is_enabled}
        visibility_txt = csv.get_row_value(row, COL_Visibility)
        visibility = self.establish_visibility(visibility_txt)
        if visibility is None:
            configurable_sku = csv.get_row_value(row, COL_ConfigurableSku)
            if configurable_sku:
                visibility = ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY
            else:
                visibility = ProductVisibilityEnum.CATALOG_AND_SEARCH
        defaults["visibility"] = visibility
        try:
            product, created = ProductConfigurable.objects.update_or_create(
                real_product=real_product, shop=self.shop, defaults=defaults
            )
        except IntegrityError:
            raise Exception(
                f"Can not create ProductConfigurable, probably already exist ProductSimple with same sku={sku}"
            )
        report["is_created"] = created
        self.import_product_features(csv, row=row, product=product)
        self.import_product_categories(csv, row=row, product=product)
        self.import_product_pictures(csv, row=row, product=product, raport=report)
        self.import_product_subproducts_config(csv, row=row, configurable_product=product)
        return report

    def update_translations_only_product_configurable(self, csv, row):
        if not self.update_translations_only:
            raise Exception("update_translations_only_product_configurable() requires self.update_translations_only")
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        try:
            real_product = RealProduct.objects.get(sku=sku)
        except RealProduct.DoesNotExist:
            return None
        product = ProductConfigurable.objects.filter(real_product=real_product, shop=self.shop).first()
        if product is None:
            return None
        report = {"product_type": "Product Configurable", "sku": sku, "is_created": False}
        self.import_product_features_t9n_only(csv, row=row, product=product)
        return report

    def import_product_subproducts_bundle(self, csv, row, bundle_product):
        subproducts_data = self.get_subproducts_skus_bundle(csv, row, COL_BundleSku)
        bundle_section_idx = csv.get_row_value(row, COL_BundleSectionIdx)

        if not subproducts_data:
            if not self.update_only:
                self.error(
                    f"Bundle Product sku={bundle_product.sku} has no subproducts skus defined in csv col={COL_BundleSku}"
                )
            return
        real_subproducts = RealProduct.objects.filter(sku__in=subproducts_data.keys())
        if len(real_subproducts) == 0:
            self.error(
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
                subproduct = ProductSimple.objects.get(real_product=real_subproduct, shop=self.shop)
                BundleLink.objects.update_or_create(
                    product_bundle=bundle_product,
                    subproduct=subproduct,
                    quantity=subproducts_data.get(subproduct.sku, 1),
                    section=bundle_section,
                )
                logger.info(
                    f"Bundle Product sku={bundle_product.sku} has been linked with {len(real_subproducts)} subproducts"
                )

            except ProductSimple.DoesNotExist:
                logger.error(
                    f'Can NOT link BundleProduct="{bundle_product}" with SimpleProduct="{real_subproduct.sku}" '
                    f'because SimpleProduct does not exist in shop="{self.shop.idx}", but RealProduct="{real_subproduct.sku}" does exist'
                )
                continue
            except Exception as e:
                print(f"{e} {real_subproduct}")

    def import_product_bundle(self, csv, row):
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        feature_set = self.get_feature_set(csv, row, sku)
        report = {"product_type": "Product Bundle", "sku": sku}
        if self.update_only:
            try:
                real_product = RealProduct.objects.get(sku=sku)
            except RealProduct.DoesNotExist:
                return None
        else:
            logger.info(f"sku: {sku}")
            real_product, created = RealProduct.objects.update_or_create(sku=sku, defaults={})

        is_enabled = csv.get_row_value(row, COL_Enabled)
        is_enabled = (
            True
            if is_enabled is None or is_enabled == "1" or is_enabled == 1 or is_enabled == True or is_enabled == "true"
            else False
        )
        defaults = {"feature_set": feature_set, "is_enabled": is_enabled}
        visibility_txt = csv.get_row_value(row, COL_Visibility)
        visibility = self.establish_visibility(visibility_txt)
        if visibility is None:
            configurable_sku = csv.get_row_value(row, COL_BundleSku)
            if configurable_sku:
                visibility = ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY
            else:
                visibility = ProductVisibilityEnum.CATALOG_AND_SEARCH
        defaults["visibility"] = visibility
        try:
            product, created = ProductBundle.objects.update_or_create(
                real_product=real_product, shop=self.shop, defaults=defaults
            )
        except IntegrityError:
            raise Exception(f"Can not create ProductBundle, probably already exist ProductSimple with same sku={sku}")
        report["is_created"] = created
        self.import_product_features(csv, row=row, product=product)
        self.import_product_categories(csv, row=row, product=product)
        self.import_product_pictures(csv, row=row, product=product, raport=report)
        self.import_product_subproducts_bundle(csv, row=row, bundle_product=product)
        return report

    def import_product_custom(self, csv, row):
        sku = self.get_product_sku(csv, row)
        if not sku:
            return None
        feature_set = self.get_feature_set(csv, row, sku)
        report = {"product_type": "Product Simple", "sku": sku}

        weight = csv.get_row_value_decimal(row, COL_Weight)
        width = csv.get_row_value_decimal(row, COL_Width)
        height = csv.get_row_value_decimal(row, COL_Height)
        deep = csv.get_row_value_decimal(row, COL_Deep)
        defaults = {}
        if weight is not None:
            defaults["weight"] = weight
        if width is not None:
            defaults["width"] = width
        if height is not None:
            defaults["height"] = height
        if deep is not None:
            defaults["deep"] = deep
        if self.update_only:
            try:
                real_product = RealProduct.objects.get(sku=sku)
            except RealProduct.DoesNotExist:
                return None
        else:
            logger.info(f"sku: {sku}")
            real_product, created = RealProduct.objects.update_or_create(sku=sku, defaults=defaults)

        f9n_set_custom_idx = csv.get_row_value(row, COL_FeatureSetCustom)

        is_enabled = csv.get_row_value(row, COL_Enabled)
        is_enabled = (
            True
            if is_enabled is None or is_enabled == "1" or is_enabled == 1 or is_enabled == True or is_enabled == "true"
            else False
        )
        defaults = {
            "feature_set": feature_set,
            "is_enabled": is_enabled,
            "customization_feature_set": FeatureSet.objects.filter(idx=f9n_set_custom_idx).first(),
        }
        visibility_txt = csv.get_row_value(row, COL_Visibility)
        visibility = self.establish_visibility(visibility_txt)
        if visibility is None:
            configurable_sku = csv.get_row_value(row, COL_ConfigurableSku)
            if configurable_sku:
                visibility = ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY
            else:
                visibility = ProductVisibilityEnum.CATALOG_AND_SEARCH
        defaults["visibility"] = visibility
        product, created = ProductCustom.objects.update_or_create(
            real_product=real_product, shop=self.shop, defaults=defaults
        )
        report["is_created"] = created
        self.import_product_features(csv, row=row, product=product)
        self.import_product_categories(csv, row=row, product=product)
        self.import_product_pictures(csv, row=row, product=product, raport=report)
        self.import_product_files(csv, row=row, product=product)
        return report

    def get_product_sku(self, csv, row):
        sku = csv.get_row_value(row, COL_SKU)
        if not sku:
            return None
        sku = normalize_sku(sku)
        return sku

    def get_product_type(self, csv, row, sku):
        types_map = {
            "simple": ProductClassEnum.ProductSimple,
            "config": ProductClassEnum.ProductConfigurable,
            "bundle": ProductClassEnum.ProductBundle,
            "custom": ProductClassEnum.ProductCustom,
        }
        product_type_csv = csv.get_row_value(row, COL_ProductType)
        if product_type_csv:
            product_type_csv = str(product_type_csv).lower().strip()
            try:
                product_type_csv = types_map[product_type_csv]
            except:
                raise Exception(f'Product type = "{product_type_csv}" is not supported')

        if sku in self.products_cache:
            product_type = self.products_cache[sku].product_class
            if (
                product_type_csv is not None
                and product_type != product_type_csv
                and not self.update_translations_only
                and not self.update_only
            ):
                if ALLOW_CHANGE_PRODUCT_TYPE:
                    # delete no matching product
                    Product.objects.filter(real_product__sku=sku, shop=self.shop).delete()
                    return product_type_csv
                else:
                    raise Exception(
                        f"Product type is changed! DB={ProductClass.label(product_type)} CSV={ProductClass.label(product_type_csv)} sku={sku}"
                    )
            return product_type
        else:
            if not product_type_csv:
                return ProductClassEnum.ProductSimple
            return product_type_csv

    def get_kind_of_product(self, csv, row, sku):
        types_map = {"physical": KindOfProductEnum.ProductPhysical, "virtual": KindOfProductEnum.ProductVirtual}
        kind_of_product_csv = None
        kind_of_product_csv_value = csv.get_row_value(row, COL_KindOfProduct)

        if kind_of_product_csv_value:
            kind_of_product_csv = str(kind_of_product_csv_value).lower().strip()
            kind_of_product_csv = types_map.get(kind_of_product_csv, None)
            if kind_of_product_csv is None:
                raise Exception(f'Kind of product = "{kind_of_product_csv_value}" is not supported')

        if sku in self.products_cache:
            kind_of_product = self.products_cache[sku].real_product.kind_of_product
            if kind_of_product_csv and kind_of_product != kind_of_product_csv:
                logger.info(
                    f"Kind of product is changed! DB={KindOfProductClass.label(kind_of_product)} CSV = {kind_of_product_csv}"
                )

        else:
            if not kind_of_product_csv:
                return KindOfProductEnum.ProductPhysical
        return kind_of_product_csv

    def import_products_type(self, csv, product_type_cls: ProductsImportBase, report):
        self.info(f"Importing {product_type_cls.name}")
        report[product_type_cls.name] = 0
        report[f"products_created_{product_type_cls.name}"] = 0

        bulk_size = CSV_IMPORT_PRODUCTS_BULK_SIZE
        products_cnt = 0
        self._threaded_cnt = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CSV_IMPORT_PRODUCTS_MAX_WORKERS) as executor:
            futures = []
            rows_bulk = []
            for row in csv:
                sku = self.get_product_sku(csv, row)
                if not sku:
                    continue
                if self.update_only and sku not in self.products_cache:
                    continue
                try:
                    product_type = self.get_product_type(csv, row, sku)
                except Exception as e:
                    logger.exception(e)
                    report["exceptions"] += 1
                    logger.error(f"Exception while getting product type: sku={sku} e={e}")
                    continue
                if product_type != product_type_cls.product_type:
                    continue
                products_cnt += 1
                if self.limit and self.limit < products_cnt:
                    self.info(f"There is row limit set to: {self.limit}")
                    break
                rows_bulk.append(row)
                if len(rows_bulk) >= bulk_size:
                    futures.append(executor.submit(product_type_cls.import_products_type_bulk, csv=csv, rows=rows_bulk))
                    rows_bulk = []
            if rows_bulk:
                futures.append(executor.submit(product_type_cls.import_products_type_bulk, csv=csv, rows=rows_bulk))
            self._threaded_total = products_cnt
            report[product_type_cls.name] = products_cnt
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    report["exceptions"] += result["exceptions"]
                    report["products_created_total"] += result["products_created"]
                    report[f"products_created_{product_type_cls.name}"] += result["products_created"]
                    report["images_total_found"] += result["images_total_found"]
                    report["images_processed_ok"] += result["images_processed_ok"]
                    report["images_processed_error"] += result["images_processed_error"]
                    report["images_unlinked"] += result["images_unlinked"]
                    report["products_without_main_image"] += result["products_without_main_image"]

        if products_cnt == 0:
            print(f"No {product_type_cls.name} products found\n", flush=True)
        else:
            print("\ndone\n", flush=True)

    def import_products(self, csv):
        report = {
            "exceptions": 0,
            "products_created_total": 0,
            "images_total_found": 0,
            "images_processed_ok": 0,
            "images_processed_error": 0,
            "images_unlinked": 0,
            "products_without_main_image": 0,
        }
        products_to_process = [
            ProductsSimpleImporter(importer=self),
            ProductsConfigurableImporter(importer=self),
            ProductsBundleImporter(importer=self),
            ProductsCustomImporter(importer=self),
        ]
        for product_type_cls in products_to_process:
            self.import_products_type(csv, product_type_cls, report)
        return report

    def link_products(self, csv):
        if self.skip_linking:
            return
        rows = []
        products_cnt = 0
        for row in csv:
            products_cnt += 1
            if self.limit and self.limit < products_cnt:
                self.info(f"There is row limit set to: {self.limit}")
                break
            rows.append(row)
        report = {"product_skipped": 0, "csv_linked_products": 0, "created_links": 0}
        self.info("Linking products from csv")
        products_link = []

        for idx, row in enumerate(rows):
            self.print_progress(idx, len(rows), "linking products")
            linked_product_dict = {}
            sku = self.get_product_sku(csv, row)
            product = Product.objects.filter(real_product__sku=sku).first()
            if not product:
                report["product_skipped"] += 1

            for col_idx, link_type in [
                [COL_Link_CrossSell, ProductLinkTypeEnum.CROSSSELL],
                [COL_Link_UpSell, ProductLinkTypeEnum.UPSELL],
                [COL_Link_Related, ProductLinkTypeEnum.RELATED],
                [COL_Link_Navigation, ProductLinkTypeEnum.NAVIGATION],
                [COL_Link_Unknown, ProductLinkTypeEnum.UNKNOWN],
            ]:
                skus_raw = csv.get_row_value_txt(row, col_idx)
                if skus_raw:
                    skus = skus_raw.split(SKU_LINK_SEPARATOR)
                    if skus:
                        linked_product_dict[link_type] = Product.objects.filter(
                            real_product__sku__in=[element.strip() for element in skus]
                        )
            for link_type, list_of_products in linked_product_dict.items():
                for product_linked in list_of_products:
                    products_link.append(
                        ProductLink(product=product, link_type=link_type, linked_product=product_linked)
                    )
        bulked_links = ProductLink.objects.bulk_create(
            products_link, batch_size=CSV_IMPORT_PRODUCTS_BULK_SIZE, ignore_conflicts=True
        )
        report["csv_linked_products"] += len(products_link)
        report["created_links"] += len(bulked_links)
        self.info(
            f"Creating Product links successfully ended. In the CSV, there were {report['csv_linked_products']} linked products, and {report['created_links']} records have been added and are in the database."
        )
        return report

    def configure_feature_text_t9n(self, csv, feature):
        # jesli update_only to nie wymagamy pol

        for lang in self.shop_languages:
            is_required = False
            if not self.update_only and feature.is_required and lang.iso2 == self.shop.default_language.iso2:
                is_required = True
            col_idx = self.generate_feature_col_idx(feature.idx, lang.iso2)
            csv.add_col_config(col_idx=col_idx, is_required=is_required)
            if not IMPORT_PRODUCTS_PIM_CSV_SKIP_FEATURES_INFO:
                self.info(
                    "  - {:28} col_idx = {:32} is_required = {}".format(feature.idx, '"' + col_idx + '"', is_required)
                )

    def configure_feature_default(self, csv, feature):
        # jesli update_only to nie wymagamy pol
        is_required = False if self.update_only else feature.is_required
        col_idx = self.generate_feature_col_idx(feature.idx)
        csv.add_col_config(col_idx=col_idx, is_required=is_required)
        if not IMPORT_PRODUCTS_PIM_CSV_SKIP_FEATURES_INFO:
            self.info(
                "  - {:28} col_idx = {:32} is_required = {}".format(feature.idx, '"' + col_idx + '"', is_required)
            )

    def configure_csv_feature(self, csv, feature):
        if feature.feature_type in (FeatureTypeEnum.TEXT_T9N, FeatureTypeEnum.VARCHAR255_T9N):
            self.configure_feature_text_t9n(csv, feature)
        elif feature.feature_type in (
            FeatureTypeEnum.BOOL,
            FeatureTypeEnum.DECIMAL,
            FeatureTypeEnum.VARCHAR255,
            FeatureTypeEnum.TEXT,
            FeatureTypeEnum.SELECT,
            FeatureTypeEnum.MULTISELECT,
            FeatureTypeEnum.TEMPERATURE,
            FeatureTypeEnum.MASS,
            FeatureTypeEnum.LENGTH,
            FeatureTypeEnum.JSON,
            FeatureTypeEnum.JSON_T9N,
            FeatureTypeEnum.DATETIME,
        ):
            self.configure_feature_default(csv, feature)
        else:
            self.error(f"Feature type={feature.feature_type_name} is not supported for idx={feature.idx}")

    def configure_csv(self, csv):
        self.info("Configuring product features:")
        for feature in Feature.objects.all().order_by("scope", "display_order", "idx"):
            self.configure_csv_feature(csv, feature)

    def ensureProcessColumnsExists(self, csv):
        for col_idx in (COL_ImportStatus, COL_ImportMessage):
            csv.ensure_column_exists(col_idx=col_idx)

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Products Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"  Shop:          {self.shop.name} [{self.shop.idx}]")
        self.info(f"  Ilość wątków:  {CSV_IMPORT_PRODUCTS_MAX_WORKERS}")
        self.info(f"  Bulk size:     {CSV_IMPORT_PRODUCTS_BULK_SIZE}")
        self.info(f"Opening csv file: {self.file_path} ...")
        ProductsImportFromCsvStartEvent(file_path=self.file_path, shop=self.shop.idx)
        bev = ProductsImportFromCsvEndEvent(file_path=self.file_path, shop=self.shop.idx)
        report = {
            "update_only": self.update_only,
            "update_translations_only": self.update_translations_only,
            "delete_attr": self.delete_attr,
        }
        try:
            csv = ProductsCsv()
            self.configure_csv(csv)
            csv.load_file(self.file_path)
            self.ensureProcessColumnsExists(csv)
            report.update(self.import_products(csv))
            report["csv_rows"] = csv.get_max_rows()
            if not self.update_only:
                report_linked = self.link_products(csv)
            now = timezone.now().replace(tzinfo=utc_tz)
            now_warsaw = now.astimezone(warsaw_tz)
            self.info(
                "Packages Import from csv is done at {} [Warsaw TZ]".format(now_warsaw.strftime("%Y-%m-%d %H:%M:%S"))
            )
            # file_path_after = '{}-after.csv'.format(self.file_path[:-5])
            # csv.savecsv(file_path_after)

            bev.set_details(report)
            bev.finish_with_success(finish_tag="CSV has been imported")
            return True
        except Exception as e:
            bev.set_details(report)
            bev.finish_with_exception(e)
            raise e
