# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.db import transaction
from django.utils import timezone
from django_pim.models import Feature, FeatureInFeatureSet, FeatureScopeEnum, FeatureSet
from django_pim.utils.idx_normalizator import normalize_idx

from ..bi import ConfigFeaturesInFeaturesSetsFromCsvEvent
from ..csv.config_features_in_features_sets import (
    COL_FEATURE,
    COL_FEATURE_SET,
    COL_POSITION,
    COL_REQUIRED,
    ConfigFeatureInFeaturesSetsCsv,
)
from .abstract import AbstractSync

logger = logging.getLogger("django")


def _flag(value: bool | None) -> str:
    return "null" if value is None else str(value).lower()


class ConfigFeaturesInFeaturesSetsImporter(AbstractSync):
    fail_if_locked = True

    def __init__(self, file_path: str, prune: bool = False, dry_run: bool = False):
        super().__init__()
        self.file_path = file_path
        self.prune = prune
        self.dry_run = dry_run
        self.bev = None
        self.report = {}
        self.langs = []
        self.required_changes = []

    def import_row(self, csv, row, row_nr):
        label = f"{csv.get_row_value(row, COL_FEATURE)} in {csv.get_row_value(row, COL_FEATURE_SET)}"
        try:
            feature = Feature.objects.get(idx=normalize_idx(csv.get_row_value(row, COL_FEATURE)))
            feature_set = FeatureSet.objects.get(idx=normalize_idx(csv.get_row_value(row, COL_FEATURE_SET)))
            position = csv.get_row_value(row, COL_POSITION)
            defaults = {"position": int(position) if position else 0}
            if csv.exists_col(COL_REQUIRED):
                defaults["is_required"] = self.parse_required(csv, row, feature)
            with transaction.atomic():
                self.record_required_change(feature, feature_set, defaults)
                FeatureInFeatureSet.objects.update_or_create(
                    feature=feature, feature_set=feature_set, defaults=defaults
                )
        except Exception as e:
            self.row_error(row_nr, f"{label}: {e}")
            return
        self.keep_links(feature_set, [feature])

    @staticmethod
    def parse_required(csv, row, feature) -> bool | None:
        value = csv.get_row_value_required(row)
        if value is not None and feature.scope == FeatureScopeEnum.SYSTEM:
            raise ValueError(f"{COL_REQUIRED} cannot be set on system feature {feature.idx}")
        return value

    def record_required_change(self, feature, feature_set, defaults) -> None:
        if "is_required" not in defaults:
            return
        current = FeatureInFeatureSet.objects.filter(feature=feature, feature_set=feature_set).first()
        before = current.is_required if current else None
        after = defaults["is_required"]
        if before != after:
            self.required_changes.append(f"set: {feature.idx} in {feature_set.idx} {_flag(before)}→{_flag(after)}")

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
