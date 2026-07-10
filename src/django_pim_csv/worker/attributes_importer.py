# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import logging
import os

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_pim.managers import PictureManager
from django_pim.models import Attribute, AttributePicture, Feature, Picture
from django_pim.settings import SYSTEM_FEATURE_NAME_IDX, T9N_DEFAULT_LANG
from django_pim.utils.idx_normalizator import normalize_idx
from django_utils.api.utils import make_media_url

from ..bi import AttributesImportFromCsvEvent
from ..csv.attributes import COL_DISPLAY_ORDER, COL_EXT, COL_GROUP_IDX, COL_IDX, AttributesCsv
from .abstract import AbstractSync

COL_ImportStatus = "import status"
COL_ImportMessage = "import message"

logger = logging.getLogger("django")


class AttributesImporter(AbstractSync):
    def __init__(self, file_path: str, feature_idx: str):
        super().__init__()
        self.file_path = file_path
        self.feature = Feature.objects.get(idx=feature_idx)
        self.bev = None
        self.report = {}

    def import_attr(self, csv, row, row_nr):
        idx = csv.get_row_value(row, COL_IDX)
        group_idx = csv.get_row_value(row, COL_GROUP_IDX)
        display_order = csv.get_row_value(row, COL_DISPLAY_ORDER)
        idx = normalize_idx(idx)
        name_t9n = {}
        feature = Feature.objects.get(idx=SYSTEM_FEATURE_NAME_IDX)
        for lang in self.langs:
            col_idx = self.generate_feature_col_idx(feature.idx, lang)
            name_t9n[lang] = csv.get_row_value(row, col_idx)

        for name, lang in name_t9n.items():
            if not lang:
                name_t9n[name] = name_t9n.get(T9N_DEFAULT_LANG, "")

        try:
            from django_pim.models import AttributesGroup

            group = AttributesGroup.objects.get(idx=group_idx)
        except ImportError:
            group = None
        except AttributesGroup.DoesNotExist:
            group = None

        extension = csv.get_row_value(row, COL_EXT)
        picture = None
        if extension:
            try:
                extension = json.loads(extension)
                if "type" in extension and "value" in extension:
                    if extension["type"] == "img":
                        picture = self.import_attr_image(extension["value"], idx)
                        if picture:
                            extension["value"] = make_media_url(str(picture.image))
            except json.JSONDecodeError:
                extension = None
        try:
            attr = Attribute.objects.get(idx=idx, feature=self.feature)
            attr.name_t9n = name_t9n
            attr.group = group
            if not attr.display_order and not display_order:
                attr.display_order = row_nr
            elif display_order:
                attr.display_order = display_order
            if extension:
                attr.extension = extension
            attr.save()
        except Attribute.DoesNotExist:
            attr = Attribute.objects.create(
                idx=idx, feature=self.feature, name_t9n=name_t9n, display_order=row_nr, extension=extension, group=group
            )
            attr.save()
            self.report["count_new"] += 1

        if picture and attr:
            attr_picture = self.save_attr_image(attr, picture)

    def import_attr_image(self, path, attr_idx=None):
        if path[0] == "/":
            full_path = path
        else:
            full_path = os.path.join(os.path.dirname(self.file_path), path)
        if not os.path.exists(full_path):
            logger.error(f'Can not import not existing picture path="{full_path}"')
            self.report["images_processed_error"] += 1
            return None

        picture = None
        try:
            picture = PictureManager.get_picture(full_path)
        except Exception as e:
            logger.exception(e)

        return picture

    def save_attr_image(self, attr: Attribute, picture: Picture):
        try:
            attr_picture = AttributePicture.objects.get(attribute=attr, picture=picture)
        except ObjectDoesNotExist:
            attr_picture = AttributePicture(attribute=attr, picture=picture)
            attr_picture.save()

        return attr_picture

    def delete_not_in_csv(self, idx_list):
        Attribute.objects.filter(feature=self.feature).exclude(idx__in=idx_list).delete()

    def import_attributes(self, csv):
        self.info("Importing Attributes:")
        row_nr = 0
        total = csv.get_max_rows()
        idx_list = []
        for row in csv:
            row_nr += 1
            self.print_progress(row_nr, total, "attributes")
            if self.limit and self.limit < row_nr:
                self.info(f"There is row limit set to: {self.limit}")
                break
            self.report["count_processed_rows"] += 1
            self.import_attr(csv=csv, row=row, row_nr=row_nr)
            idx_list.append(csv.get_row_value(row, COL_IDX))
            print(".", end="", flush=True)

        self.delete_not_in_csv(idx_list)

        print(" done")

    def configure_csv(self, csv):
        self.info("Configuring name column:")
        feature = Feature.objects.get(idx=SYSTEM_FEATURE_NAME_IDX)
        self.configure_column_text_t9n(csv, feature.idx)

    def ensureProcessColumnsExists(self, csv):
        for col_idx in (COL_ImportStatus, COL_ImportMessage):
            csv.ensure_column_exists(col_idx=col_idx)

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Attributes Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"Opening csv file: {self.file_path} ...")
        self.bev = AttributesImportFromCsvEvent(
            file_path=self.file_path, feature_idx=self.feature.idx, is_ongoing_event=True
        )
        self.report = {"count_processed_rows": 0, "count_new": 0, "images_processed_error": 0}
        try:
            csv = AttributesCsv()
            self.configure_csv(csv)
            csv.load_file(self.file_path)
            self.ensureProcessColumnsExists(csv)
            self.import_attributes(csv)

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
