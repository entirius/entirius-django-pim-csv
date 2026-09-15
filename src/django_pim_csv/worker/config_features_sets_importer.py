# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.db import transaction
from django.utils import timezone
from django_pim.models import Feature, FeatureSet
from django_pim.utils.idx_normalizator import normalize_idx

from ..bi import ConfigImportFromCsvEvent
from ..csv.config_features_sets import COL_DESC, COL_FEATURES, COL_IDX, COL_IS_DEFAULT, COL_NAME, ConfigFeaturesSetsCsv
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ConfigFeaturesSetsImporter(AbstractSync):
    fail_if_locked = True

    def __init__(self, file_path: str, prune: bool = False, dry_run: bool = False):
        super().__init__()
        self.file_path = file_path
        self.prune = prune
        self.dry_run = dry_run
        self.bev = None
        self.report = {}

    def import_row(self, csv, row, row_nr):
        features = []
        try:
            idx = normalize_idx(csv.get_row_value(row, COL_IDX))
            name = csv.get_row_value(row, COL_NAME)
            desc = csv.get_row_value(row, COL_DESC)
            if not desc:
                desc = ""
            is_default = csv.get_row_value_bool(row, COL_IS_DEFAULT, default=False)
            features_raw = csv.get_row_value_txt(row, COL_FEATURES)
            for feature_idx in features_raw.split(","):
                if not feature_idx.strip():
                    continue
                feature_idx = normalize_idx(feature_idx)
                try:
                    features.append(Feature.objects.get(idx=feature_idx))
                except Feature.DoesNotExist:
                    self.row_error(row_nr, f"feature {feature_idx} does not exist (set {idx})")
        except Exception as e:
            self.row_error(row_nr, f"invalid data: {e}")
            return

        try:
            with transaction.atomic():
                feature_set, created = FeatureSet.objects.update_or_create(
                    idx=idx, defaults={"name": name, "desc": desc, "is_default": is_default}
                )
                feature_set.features.add(*features)
        except Exception as e:
            self.row_error(row_nr, f"set {idx}: {e}")
            return
        print("FeatureSet has Features:")
        for feature in features:
            print(f"    - {feature.idx}")

        if created:
            self.report["count_new"] += 1
        self.keep_links(feature_set, features)

    def load_data(self, csv):
        self.info("Importing:")
        row_nr = 0
        total = csv.get_max_rows()
        for row in csv:
            row_nr += 1
            self.print_progress(row_nr, total, "channels")
            if self.limit and self.limit < row_nr:
                self.info(f"There is row limit set to: {self.limit}")
                break
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
        self.bev = ConfigImportFromCsvEvent(file_path=self.file_path)
        self.report = {"count_processed_rows": 0, "count_new": 0}
        try:
            csv = ConfigFeaturesSetsCsv()
            csv.load_file(self.file_path)
            self.load_atomically(csv)
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
