# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.utils import timezone
from django_pim.models import Shop
from django_pim.utils.idx_normalizator import normalize_idx
from django_regional.models import Currency, Language

from ..bi import ConfigImportFromCsvEvent
from ..csv.config_channels import (
    COL_CURRENCIES,
    COL_DEFAULT_CURRENCY,
    COL_DEFAULT_LANGUAGE,
    COL_IDX,
    COL_LANGUAGES,
    COL_NAME,
    ConfigChannelsCsv,
)
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ConfigChannelsImporter(AbstractSync):
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.bev = None
        self.report = {}

    def import_row(self, csv, row, row_nr):
        try:
            idx = normalize_idx(csv.get_row_value(row, COL_IDX))
            name = csv.get_row_value(row, COL_NAME)
            default_language = Language.getFromIso2(csv.get_row_value(row, COL_DEFAULT_LANGUAGE))
            default_currency = Currency.getFromiso3(csv.get_row_value(row, COL_DEFAULT_CURRENCY))
            languages = []
            languages_raw = csv.get_row_value_txt(row, COL_LANGUAGES)
            for lang in languages_raw.split(","):
                languages.append(Language.getFromIso2(lang))
            currencies = []
            currencies_raw = csv.get_row_value_txt(row, COL_CURRENCIES)
            for curr in currencies_raw.split(","):
                currencies.append(Currency.getFromiso3(curr))
        except Exception as e:
            raise Exception(f"Invalid data in row {row} {row_nr}: {e}")

        shop, created = Shop.objects.update_or_create(
            idx=idx, defaults={"name": name, "default_language": default_language, "default_currency": default_currency}
        )
        if created:
            self.report["count_new"] += 1

        shop.languages.add(*languages)
        shop.currencies.add(*currencies)

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
            csv = ConfigChannelsCsv()
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
