# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_pim.models import Feature, FeatureSet
from django_pim.utils.idx_normalizator import normalize_idx

from ..bi import ConfigFeaturesInFeaturesSetsFromCsvEvent
from ..csv.config_features_in_features_sets import (
    COL_FEATURE,
    COL_FEATURE_SET,
    COL_POSITION,
    ConfigFeatureInFeaturesSetsCsv,
)
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ConfigFeaturesInFeaturesSetsImporter(AbstractSync):
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.bev = None
        self.report = {}
        self.langs = []

    def import_row(self, csv, row, row_nr):

        feature_idx = normalize_idx(csv.get_row_value(row, COL_FEATURE))
        feature_set_idx = normalize_idx(csv.get_row_value(row, COL_FEATURE_SET))
        try:
            feature = Feature.objects.get(idx=feature_idx)
            feature_set = FeatureSet.objects.get(idx=feature_set_idx)
        except ObjectDoesNotExist as e:
            raise Exception(f"Invalid data in row {row} {row_nr}: {e}")

        try:
            # if through tabel FeatureInFeatureSet model is not available (add in 1.11 pim) then use Feature model
            from django_pim.models import FeatureInFeatureSet

            position = csv.get_row_value(row, COL_POSITION)
            position = int(position) if position else 0
            FeatureInFeatureSet.objects.update_or_create(
                feature=feature, feature_set=feature_set, defaults={"position": position}
            )
        except ImportError:
            feature.features_sets.add(feature_set)
        except Exception as e:
            raise Exception(f"Invalid data in row {row} {row_nr}: {e}")

    def load_data(self, csv):
        self.info("Importing:")
        row_nr = 0
        total = csv.get_max_rows()
        for row in csv:
            row_nr += 1
            self.print_progress(row_nr, total, "channels")
            self.report["count_processed_rows"] += 1
            self.import_row(csv=csv, row=row, row_nr=row_nr)
            print(".", end="", flush=True)
        print(" done")

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Config PIM Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"Opening csv file: {self.file_path} ...")
        self.bev = ConfigFeaturesInFeaturesSetsFromCsvEvent(file_path=self.file_path)
        self.report = {"count_processed_rows": 0, "count_new": 0}
        try:
            csv = ConfigFeatureInFeaturesSetsCsv()
            csv.load_file(self.file_path)
            self.load_data(csv)

            now = timezone.now().replace(tzinfo=utc_tz)
            now_warsaw = now.astimezone(warsaw_tz)
            self.info(
                "Config PIM Import from csv is done at {} [Warsaw TZ]".format(now_warsaw.strftime("%Y-%m-%d %H:%M:%S"))
            )
            self.bev.set_details(self.report)
            self.bev.finish_with_success(finish_tag="CSV has been imported")
            return True
        except Exception as e:
            self.bev.set_details(self.report)
            self.bev.finish_with_exception(e)
            raise e
