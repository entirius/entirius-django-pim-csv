# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging

import pytz
from django.db.models import Q
from django.utils import timezone
from django_pim.models import Attribute, AttributeModifier, AttributesGroup, Feature, Product, RealProduct, Shop
from django_pim.models.attribute import AttributeModifierType, AttributeModifierTypeEnum
from django_pim.utils.idx_normalizator import normalize_idx
from tqdm import tqdm

from ..bi import CustomModifierAttributesImportFromCsvEvent
from ..csv.custom_modifier_attributes import (
    COL_ATTRIBUTE_COERCED_IDX,
    COL_ATTRIBUTE_IDX,
    COL_ATTRIBUTE_MODIFIED_IDX,
    COL_FEATURE_IDX,
    COL_FEATURE_MODIFIED_IDX,
    COL_GROUP_IDX,
    COL_HASH,
    COL_SKU,
    COL_TYPE,
    CustomModifierAttributesCsv,
)
from .abstract import AbstractSync

COL_ImportStatus = "import status"
COL_ImportMessage = "import message"

logger = logging.getLogger("process")


class CustomModifiersAttributesImporter(AbstractSync):
    def __init__(self, file_path: str, shop_id: int | None = None, shop_idx: str | None = None):
        self.lock_file = False
        super().__init__()
        self.file_path = file_path
        self.bev = None
        self.report = {}
        if shop_id is not None:
            self.shop = Shop.objects.get(id=shop_id)
        elif shop_idx is not None:
            self.shop = Shop.objects.get(idx=shop_idx)

    @staticmethod
    def _normalize_if_not_none(value):
        if value:
            return normalize_idx(value)
        return None

    def import_custom_modifier_attributes(self, csv):
        self.info("Importing Custom Modifier Attributes:")
        row_nr = 0
        total = csv.get_max_rows()

        existing_hashes = set(
            AttributeModifier.objects.filter(Q(product__shop=self.shop) | Q(product__shop=None)).values_list(
                "csv_row_hash", flat=True
            )
        )

        csv_row_hash_in_db = list(
            AttributeModifier.objects.filter(Q(product__shop=self.shop) | Q(product__shop=None)).values_list(
                "csv_row_hash", flat=True
            )
        )

        for idx, row in tqdm(enumerate(csv), total=total):
            string_row = str(row)
            csv_row_hash_external = csv.get_row_value(row, COL_HASH)
            csv_row_hash = csv_row_hash_external
            if not csv_row_hash:
                csv_row_hash = hashlib.md5(string_row.encode("utf-8")).hexdigest()
            idx = idx + 1

            if csv_row_hash in existing_hashes:
                csv_row_hash_in_db.remove(csv_row_hash) if csv_row_hash in csv_row_hash_in_db else None
                continue

            try:
                row_nr += 1
                self.print_progress(row_nr, total, "custom_modifier_attributes", every=10000)
                if self.limit and self.limit < row_nr:
                    self.info(f"There is row limit set to: {self.limit}")
                    break
                self.report["count_processed_rows"] += 1

                sku = csv.get_row_value(row, COL_SKU)
                feature_idx = self._normalize_if_not_none(csv.get_row_value(row, COL_FEATURE_IDX))

                all_attributes = []
                start_attr_idx = 0
                while True:
                    if f"{COL_ATTRIBUTE_IDX}_{start_attr_idx}" not in csv.cols:
                        break

                    attribute_idx = self._normalize_if_not_none(
                        csv.get_row_value(row, f"{COL_ATTRIBUTE_IDX}_{start_attr_idx}")
                    )
                    if attribute_idx:
                        all_attributes.append(attribute_idx)
                    start_attr_idx += 1

                start_group_idx = 0
                all_groups = []
                while True:
                    if f"{COL_GROUP_IDX}_{start_group_idx}" not in csv.cols:
                        break

                    group_idx = self._normalize_if_not_none(
                        csv.get_row_value(row, f"{COL_GROUP_IDX}_{start_group_idx}")
                    )
                    if group_idx:
                        all_groups.append(group_idx)
                    start_group_idx += 1

                attribute_modified_idx = self._normalize_if_not_none(csv.get_row_value(row, COL_ATTRIBUTE_MODIFIED_IDX))
                attribute_coerced_idx = self._normalize_if_not_none(csv.get_row_value(row, COL_ATTRIBUTE_COERCED_IDX))
                feature_modified_idx = self._normalize_if_not_none(csv.get_row_value(row, COL_FEATURE_MODIFIED_IDX))
                if not csv.get_row_value(row, COL_TYPE):
                    continue
                try:
                    modifier_type = AttributeModifierType.get_modifier_type_int(csv.get_row_value(row, COL_TYPE))
                except ValueError:
                    logger.error(f"Modifier Type invalid: {csv.get_row_value(row, COL_TYPE)}, idx: {idx}")
                    continue
                product = Product.objects.filter(real_product__sku=sku, shop=self.shop).first()
                real_product = RealProduct.objects.filter(sku=sku).first()

                if sku and not real_product:
                    logger.error(f"Product not found: {sku}, idx: {idx}")
                    continue

                attributes = Attribute.objects.filter(idx__in=all_attributes)
                attributes_leak = list(
                    set(all_attributes).symmetric_difference(set(attributes.values_list("idx", flat=True)))
                )
                if attributes_leak:
                    logger.error(f"Attributes Modifier not found: {attributes_leak} for idx: {idx}")

                feature = Feature.objects.filter(idx=feature_idx).first()
                if feature_idx and not feature:
                    logger.error(f"Feature not found: {feature_idx}, idx: {idx}")
                    continue

                attribute_modified = Attribute.objects.filter(idx=attribute_modified_idx).first()
                if attribute_modified_idx and not attribute_modified:
                    logger.error(f"Attribute Modified not found: {attribute_modified_idx}, idx: {idx}")
                    continue

                attribute_coerced = Attribute.objects.filter(idx=attribute_coerced_idx).first()
                if attribute_coerced_idx and not attribute_coerced:
                    logger.error(f"Attribute coerced not found: {attribute_coerced_idx}, idx: {idx}")
                    continue

                feature_modified = Feature.objects.filter(idx=feature_modified_idx).first()
                if feature_modified_idx and not feature_modified:
                    logger.error(f"Feature Modified not found: {feature_modified_idx}, idx: {idx}")
                    continue

                groups = AttributesGroup.objects.filter(idx__in=all_groups)
                attributes_leak = list(
                    set(all_attributes).symmetric_difference(set(attributes.values_list("idx", flat=True)))
                )
                if attributes_leak:
                    logger.error(f"Attributes Modifier not found: {attributes_leak} for idx: {idx}")
                    continue

                if modifier_type in [
                    AttributeModifierTypeEnum.EXCLUDE,
                    AttributeModifierTypeEnum.COLOR_HASH_INTERSECTION,
                    AttributeModifierTypeEnum.DEFAULT,
                    AttributeModifierTypeEnum.COERCE,
                ]:
                    attr, is_created = AttributeModifier.objects.create_or_update(
                        product=product,
                        real_product=real_product,
                        feature=feature,
                        attributes=attributes,
                        feature_modified=feature_modified,
                        attribute_modified=attribute_modified,
                        attribute_coerced=attribute_coerced,
                        groups=groups,
                        modifier_type=modifier_type,
                        idx=idx,
                        value_modifier=None,
                        csv_row_hash=csv_row_hash,
                    )
                    if is_created:
                        self.report["count_new"] += 1

                    csv_row_hash_in_db.remove(csv_row_hash) if csv_row_hash in csv_row_hash_in_db else None

                elif modifier_type == AttributeModifierTypeEnum.VALUE:
                    for idx_value, (col, col_idx) in enumerate(csv.cols_index.items()):
                        if col in csv.cols:
                            continue

                        value_modifier = csv.get_row_value(row, col)
                        if not value_modifier:
                            continue

                        try:
                            feature_modified = Feature.objects.filter(idx=self._normalize_if_not_none(col)).first()
                        except Feature.DoesNotExist:
                            continue

                        if value_modifier:
                            attr, is_created = AttributeModifier.objects.create_or_update(
                                product=product,
                                real_product=real_product,
                                feature=feature,
                                attributes=attributes,
                                feature_modified=feature_modified,
                                attribute_modified=attribute_modified,
                                attribute_coerced=attribute_coerced,
                                groups=groups,
                                modifier_type=modifier_type,
                                idx=idx,
                                value_modifier=value_modifier,
                                csv_row_hash=csv_row_hash,
                            )
                            if is_created:
                                self.report["count_new"] += 1

                            csv_row_hash_in_db.remove(csv_row_hash) if csv_row_hash in csv_row_hash_in_db else None

            except Exception as e:
                logger.exception(e)
                raise e

        print(" done")

        # delete not updated
        AttributeModifier.objects.filter(csv_row_hash__in=csv_row_hash_in_db).filter(
            Q(product__shop=self.shop) | Q(product__shop=None)
        ).delete()

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Custom Modifier Attributes Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"Opening csv file: {self.file_path} ...")
        self.bev = CustomModifierAttributesImportFromCsvEvent(file_path=self.file_path, is_ongoing_event=True)
        self.report = {"count_processed_rows": 0, "count_new": 0}
        try:
            csv = CustomModifierAttributesCsv()
            csv.load_file(self.file_path)
            self.import_custom_modifier_attributes(csv)

            now = timezone.now().replace(tzinfo=utc_tz)
            now_warsaw = now.astimezone(warsaw_tz)
            self.info(
                "Packages Import from csv is done at {} [Warsaw TZ]".format(now_warsaw.strftime("%Y-%m-%d %H:%M:%S"))
            )
            self.bev.set_details(self.report)
            self.bev.finish_with_success(finish_tag="CSV has been imported")
            return True
        except Exception as e:
            self.bev.set_details(self.report)
            self.bev.finish_with_exception(e)
            raise e
