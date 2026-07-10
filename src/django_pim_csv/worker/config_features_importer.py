# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.utils import timezone
from django_pim.models import Feature, FeatureScopeEnum, FeatureTypeEnum, FrontendInputTypeEnum
from django_pim.settings import SYSTEM_FEATURES_IDXS
from django_pim.utils.idx_normalizator import normalize_idx
from slugify import slugify

from ..bi import ConfigImportFromCsvEvent
from ..csv.config_features import (
    COL_FRONTEND_INPUT_TYPE,
    COL_IDX,
    COL_IS_COMPARABLE,
    COL_IS_FILTERABLE,
    COL_IS_REQUIRED,
    COL_IS_SEARCHABLE,
    COL_IS_VISIBLE,
    COL_SCOPE,
    COL_TYPE,
    ConfigFeaturesCsv,
)
from ..settings import IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM, T9N_DEFAULT_LANG
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ConfigFeaturesImporter(AbstractSync):
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.bev = None
        self.report = {}
        self.langs = []
        self.init_langs()

    def import_row(self, csv, row, row_nr):
        def discover_scope(text, feature_idx):
            ftype_map = {
                "system": FeatureScopeEnum.SYSTEM,
                "global": FeatureScopeEnum.BUSINESS_UNIT,  # GLOBAL deprecated, treat as BU
                "business_unit": FeatureScopeEnum.BUSINESS_UNIT,
            }
            text = text.lower().strip()
            if feature_idx in SYSTEM_FEATURES_IDXS:
                return FeatureScopeEnum.SYSTEM
            if text in ftype_map:
                return ftype_map[text]
            return FeatureScopeEnum.BUSINESS_UNIT

        ftype_map = {
            "text": FeatureTypeEnum.TEXT,
            "t9n": FeatureTypeEnum.TEXT_T9N,
            "text-t9n": FeatureTypeEnum.TEXT_T9N,
            "varchar-255": FeatureTypeEnum.VARCHAR255,
            "varchar-255-t9n": FeatureTypeEnum.VARCHAR255_T9N,
            "multiselect": FeatureTypeEnum.MULTISELECT,
            "select": FeatureTypeEnum.SELECT,
            "bool": FeatureTypeEnum.BOOL,
            "decimal": FeatureTypeEnum.DECIMAL,
            "datetime": FeatureTypeEnum.DATETIME,
            "temperature": FeatureTypeEnum.TEMPERATURE,
            "length": FeatureTypeEnum.LENGTH,
            "mass": FeatureTypeEnum.MASS,
            "json": FeatureTypeEnum.JSON,
            "json-t9n": FeatureTypeEnum.JSON_T9N,
        }

        def discover_feature_type(text):
            text = slugify(text, separator="-").lower()
            if text in ftype_map:
                return ftype_map[text]
            raise Exception(f"Unknown feature type: {text} in row: {row}")

        def discover_frontend_input_type(text):
            frontend_input_type_map = {
                "default": FrontendInputTypeEnum.DEFAULT,
                "dropdown": FrontendInputTypeEnum.DROPDOWN,
                "dropdown with price": FrontendInputTypeEnum.DROPDOWN_WITH_PRICE,
                "palette color": FrontendInputTypeEnum.PALETTE_COLOR,
                "slider": FrontendInputTypeEnum.SLIDER,
                "select swatch visual": FrontendInputTypeEnum.SELECT_SWATCH_VISUAL,
                "select swatch text": FrontendInputTypeEnum.SELECT_SWATCH_TEXT,
            }
            if text is None:
                return FrontendInputTypeEnum.DEFAULT
            text = slugify(text, separator=" ").lower()
            if text in frontend_input_type_map:
                return frontend_input_type_map[text]
            raise Exception(f"Unknown frontend input type: {text} in row: {row}")

        def does_text_value_exist(value):
            if value is None:
                return False
            value = str(value)
            value.strip()
            if not value:
                return False
            return True

        def compose_name_t9n():
            feature_idx = "name"
            value_t9n = {}
            obj_exists = False
            dt_col_idx = self.generate_feature_col_idx(feature_idx, T9N_DEFAULT_LANG)
            dt_value = csv.get_row_value(row, dt_col_idx)
            dt_exists = does_text_value_exist(dt_value)
            for lang in self.langs:
                col_idx = self.generate_feature_col_idx(feature_idx, lang)
                value = csv.get_row_value(row, col_idx)
                exists = does_text_value_exist(value)
                if exists:
                    obj_exists = True
                    value_t9n[lang] = str(value).strip()
                elif dt_exists:
                    value_t9n[lang] = str(dt_value).strip()
            if not obj_exists:
                value_t9n = None
            return value_t9n

        try:
            self.init_langs()
            idx = normalize_idx(csv.get_row_value(row, COL_IDX))
            name_t9n = compose_name_t9n()
            feature_type = discover_feature_type(csv.get_row_value(row, COL_TYPE))
            frontend_input_type = discover_frontend_input_type(csv.get_row_value(row, COL_FRONTEND_INPUT_TYPE))
            scope = discover_scope(csv.get_row_value(row, COL_SCOPE), idx)
            is_filterable = csv.get_row_value_bool(row, COL_IS_FILTERABLE, default=False)
            is_searchable = csv.get_row_value_bool(row, COL_IS_SEARCHABLE, default=False)
            is_required = csv.get_row_value_bool(row, COL_IS_REQUIRED, default=False)
            is_comparable = csv.get_row_value_bool(row, COL_IS_COMPARABLE, default=False)
            is_visible = csv.get_row_value_bool(row, COL_IS_VISIBLE, default=False)
        except Exception as e:
            raise Exception(f"Invalid data in row {row} {row_nr}: {e}")

        feature = Feature.objects.filter(idx=idx).first()
        if feature is not None:
            if feature.scope != scope:
                print(f"Can not change existing features scope, row={row}")
                logger.exception(f"Can not change existing features scope, row={row}")
                return

            # import featureów z magento musi umiec nadawać im typy
            # if feature.feature_type != feature_type:
            #     print("Can not change existing feature type, row={}".format(row))
            #     logger.exception("Can not change existing feature type, row={}".format(row))
            #     return

        try:
            feature, created = Feature.objects.update_or_create(
                idx=idx,
                defaults={
                    "name_t9n": name_t9n,
                    "scope": scope,
                    "feature_type": feature_type,
                    "is_required": is_required,
                    "is_filterable": is_filterable,
                    "is_searchable": is_searchable,
                    "is_comparable": is_comparable,
                    "frontend_input_type": frontend_input_type,
                    "is_visible": is_visible,
                },
            )
            if created:
                self.report["count_new"] += 1
        except Exception as e:
            logger.error(f"Error in row {row_nr}: {e}")

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

    def configure_csv(self, csv):
        feature_idx = "name"
        for lang in self.langs:
            shop_default_lang = getattr(getattr(getattr(self, "shop", None), "default_language", None), "iso2", None)
            default_lang = (
                shop_default_lang if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM and shop_default_lang else T9N_DEFAULT_LANG
            )
            is_required = True if lang == default_lang else False
            col_idx = self.generate_feature_col_idx(feature_idx, lang)
            csv.add_col_config(col_idx=col_idx, is_required=is_required)
            self.info(
                "  - {:28} col_idx = {:32} is_required = {}".format(feature_idx, '"' + col_idx + '"', is_required)
            )

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
            csv = ConfigFeaturesCsv()
            self.configure_csv(csv)
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
