# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import os

import pytz
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils import timezone
from django_pim.managers import PictureManager
from django_pim.models import PictureRoleEnum, ProductCategory, ProductCategoryPicture, Shop
from django_pim.utils.idx_normalizator import normalize_idx

from django_pim_csv.settings import IMAGE_CATEGORY_SEPARATOR

from ..bi import CategoriesImportFromCsvEvent
from ..csv.categories import (
    CategoriesCsv,
    COL_Base_Description,
    COL_Base_MetaDescription,
    COL_Base_MetaTitle,
    COL_Base_Name,
    COL_Base_UrlKey,
    COL_Extension,
    COL_External_Id,
    COL_idx,
    COL_ImgMain,
    COL_Is_Active,
    COL_Is_In_Menu,
    COL_Parent,
    COL_Position,
)
from .abstract import AbstractSync

COL_ImportStatus = "import status"
COL_ImportMessage = "import message"

logger = logging.getLogger("django")


class CategoriesImporter(AbstractSync):
    def __init__(self, file_path: str, shop_id: int | None = None, shop_idx: str | None = None):
        super().__init__()
        """
        shop_idx_path jest to identyfikator sklepu w formacie: 'BusinessUnit.idx'.'Shop.idx' ex: 'acme.shop_idx'
        """
        params_quantity = len({id(shop_id), id(shop_idx)} - {id(None)})
        if params_quantity != 1:
            raise ValueError("Exactly one of: shop_id or shop_idx_path must be set")
        if shop_id is not None:
            self.shop = Shop.objects.get(id=shop_id)
        elif shop_idx is not None:
            self.shop = Shop.objects.get(idx=shop_idx)
        else:
            raise Exception("should not happened")
        self.file_path = file_path
        self.configurable_sku_map = {}
        self.cache_idxs = []
        self.bev = None
        self.report = {}
        self.shop_langs = list(self.shop.languages.all().values_list("iso2", flat=True))
        self.required_t9n_fields = [
            ("url_key_t9n", "url_key", "Frontend routing will not work for these languages."),
            ("name_t9n", "name", "Category will display without a name for these languages."),
        ]

    def import_category_picture(self, csv, img_main, category):
        validate = URLValidator()
        if img_main[:7] == "http://" or img_main[:8] == "https://" or img_main[:6] == "ftp://":
            url = img_main
            try:
                validate(url)
            except ValidationError:
                logger.warning(f"Ignoring invalid picture url: {url}")
            picture, _ = PictureManager.download_picture(img_main)
        else:
            if len(img_main_split := img_main.split(IMAGE_CATEGORY_SEPARATOR)) > 1:
                img_main = img_main_split[0]

            if img_main == "":
                return
            elif img_main[0] == "/":
                full_path = img_main
            else:
                full_path = os.path.join(os.path.dirname(self.file_path), img_main)
            if not os.path.exists(full_path):
                logger.error(f'Can not import not existing picture path="{full_path}"')
            picture = PictureManager.get_picture(full_path)
        try:
            picture_role = PictureRoleEnum.MAIN
            ProductCategoryPicture.objects.update_or_create(
                product_category=category, picture=picture, defaults={"picture_role": picture_role}
            )
        except Exception as e:
            logger.error(f"Error while importing picture path={img_main}, e={e}")

    def validate_t9n_field(self, field_name: str, value_t9n: dict, idx: str, row_nr: int, hint: str) -> None:
        """Validate that a t9n field is not empty for the shop's languages."""
        missing_langs = [lang for lang in self.shop_langs if not value_t9n.get(lang)]
        if missing_langs:
            self.error(
                f"Category idx={idx} (row={row_nr}) has empty {field_name} for shop languages: {missing_langs}. {hint}"
            )

    def validate_row(self, idx: str, category: dict, row_nr: int) -> None:
        for field_key, field_name, hint in self.required_t9n_fields:
            self.validate_t9n_field(field_name, category[field_key], idx, row_nr, hint)

    def import_all_rows(self, csv, row, categories_dict, row_nr=1):
        idx = csv.get_row_value(row, COL_idx)
        if not idx:
            return
        idx = normalize_idx(idx)
        category = {}
        position = csv.get_row_value_int(row, COL_Position)
        category["position"] = position if position else row_nr
        category["is_in_menu"] = csv.get_row_value_bool(row, COL_Is_In_Menu, False)
        category["is_active"] = csv.get_row_value_bool(row, COL_Is_Active, False)
        category["name_t9n"] = csv.get_row_value_t9n(row, COL_Base_Name, self.langs)
        category["description_t9n"] = csv.get_row_value_t9n(row, COL_Base_Description, self.langs)
        category["meta_title_t9n"] = csv.get_row_value_t9n(row, COL_Base_MetaTitle, self.langs)
        category["meta_description_t9n"] = csv.get_row_value_t9n(row, COL_Base_MetaDescription, self.langs)
        category["external_id"] = csv.get_row_value_txt(row, COL_External_Id)
        category["url_key_t9n"] = csv.get_row_value_t9n(row, COL_Base_UrlKey, self.langs)
        category["extension"] = csv.get_row_value_json(row, COL_Extension)
        category["is_created"] = False
        category["img_main"] = csv.get_row_value_txt(row, COL_ImgMain)
        self.validate_row(idx, category, row_nr)
        parent_idx = csv.get_row_value_txt(row, COL_Parent)
        # objscie problemu, ze dla id=2 jest to kategoria w Magento root i nie jest w plikach
        # Kloczi obiecal poprawic w plikach exportu z Magento 2023-12-11
        # Kloczi poprawil dnia 2023-12-20
        # if parent_idx == "2":
        #    parent_idx = None
        category["parent_idx"] = parent_idx
        categories_dict[idx] = category
        return categories_dict

    def import_category(self, value, category):

        def update_value_t9n(orig_t9n, value_t9n):
            orig_t9n = dict(orig_t9n)
            for lang, value in value_t9n.items():
                if value:
                    orig_t9n[lang] = value
            return orig_t9n

        idx = value
        position = category[value]["position"]
        is_in_menu = category[value]["is_in_menu"]
        is_active = category[value]["is_active"]
        name_t9n = category[value]["name_t9n"]
        description_t9n = category[value]["description_t9n"]
        meta_title_t9n = category[value]["meta_title_t9n"]
        meta_description_t9n = category[value]["meta_description_t9n"]
        external_id = category[value]["external_id"]
        url_key_t9n = category[value]["url_key_t9n"]
        parent_idx = category[value]["parent_idx"]
        extension = category[value]["extension"]
        if parent_idx is not None and parent_idx != "" and parent_idx in category:
            self.import_category(parent_idx, category)
        elif parent_idx is None and parent_idx == "":
            parent_idx = None

        if parent_idx is not None and any(
            [parent_idx not in self.cache_idxs, ProductCategory.objects.filter(idx=parent_idx).count() == 0]
        ):
            parent_idx = None
        parent_category = None

        if parent_idx is None:
            tree_deep = 0
        else:
            parent_category, _ = ProductCategory.objects.get_or_create(
                shop=self.shop, idx=parent_idx, defaults={"name_t9n": {}, "is_active": False, "is_in_menu": False}
            )
            tree_deep = parent_category.tree_deep + 1

        existing_category = ProductCategory.objects.filter(shop=self.shop, idx=idx).first()
        if existing_category is not None:
            # updatujemy wartosci t9n zostawiajac dane jezykow dla ktorych nie mamy updatu
            name_t9n = update_value_t9n(existing_category.name_t9n, name_t9n)
            url_key_t9n = update_value_t9n(existing_category.url_key_t9n, url_key_t9n)
            description_t9n = update_value_t9n(existing_category.description_t9n, description_t9n)
            meta_title_t9n = update_value_t9n(existing_category.meta_title_t9n, meta_title_t9n)
            meta_description_t9n = update_value_t9n(existing_category.meta_description_t9n, meta_description_t9n)

        category, created = ProductCategory.objects.update_or_create(
            shop=self.shop,
            idx=idx,
            defaults={
                "parent_category": parent_category,
                "name_t9n": name_t9n,
                "url_key_t9n": url_key_t9n,
                "description_t9n": description_t9n,
                "meta_title_t9n": meta_title_t9n,
                "meta_description_t9n": meta_description_t9n,
                "position": position,
                "is_active": is_active,
                "is_in_menu": is_in_menu,
                "external_id": external_id,
                "extension": extension,
                "tree_deep": tree_deep,
            },
        )
        return category
        # self.import_category_picture(csv, row=row, category=category)

    def get_category_depth(self, idx, categories_dict, memo=None):
        """
        Oblicza głębokość kategorii w drzewie.
        Kategorie bez rodzica mają głębokość 0.
        """
        if memo is None:
            memo = {}
        if idx in memo:
            return memo[idx]

        category = categories_dict.get(idx)
        if not category:
            memo[idx] = 0
            return 0

        parent_idx = category.get("parent_idx")
        if not parent_idx or parent_idx == "":
            depth = 0
        else:
            depth = self.get_category_depth(parent_idx, categories_dict, memo) + 1

        memo[idx] = depth
        return depth

    def init_idx_cache(self, csv):
        self.info("Initializing categories idx cache ...")
        self.cache_idxs = []
        row_nr = 0
        for row in csv:
            row_nr += 1
            idx = csv.get_row_value_txt(row, COL_idx)
            idx = normalize_idx(idx)
            self.cache_idxs.append(idx)
        self.info("done")

    def import_categories(self, csv):
        self.init_idx_cache(csv)
        self.info("Importing Categories:")
        total = csv.get_max_rows()
        row_nr = 0
        categories_dict = {}
        for row in csv:
            row_nr += 1
            self.print_progress(row_nr, total, "categories")
            if self.limit and self.limit < row_nr:
                self.info(f"There is row limit set to: {self.limit}")
                break
            try:
                categories_dict = self.import_all_rows(csv=csv, row=row, categories_dict=categories_dict, row_nr=row_nr)
            except ValueError as e:
                print(f"ERROR TODO: obsluga bledow: e: {e}")

        self.info("Sorting categories by tree depth...")
        depth_memo = {}
        sorted_idxs = sorted(
            categories_dict.keys(), key=lambda idx: self.get_category_depth(idx, categories_dict, depth_memo)
        )
        self.info(
            f"Categories sorted. Processing {len(sorted_idxs)} categories in order: parents first, then children."
        )

        for idx in sorted_idxs:
            value = categories_dict[idx]
            try:
                category = self.import_category(idx, categories_dict)
                self.import_category_picture(csv, value["img_main"], category=category)
            except ValueError as e:
                print(f"ERROR TODO: obsluga bledow: e: {e}")
            print(".", end="", flush=True)
        self.info("done")

        self.delete_categories()

    def delete_categories(self):
        if not self.delete:
            return
        to_delete = ProductCategory.objects.filter(shop=self.shop).exclude(idx__in=self.cache_idxs)
        to_delete_list = list(to_delete.values_list("idx", flat=True))
        self.info(
            f"Deleting Categories not existing in CSV: shop={self.shop}, cnt={len(to_delete)}, categories idx={to_delete_list}"
        )
        to_delete.delete()

    def configure_feature(self, csv, feature):
        return

    def configure_csv(self, csv):
        self.info("Configuring columns:")
        self.configure_column_text_t9n(csv, COL_Base_Name)
        self.configure_column_text_t9n(csv, COL_Base_Description)
        self.configure_column_text_t9n(csv, COL_Base_UrlKey)

    def ensureProcessColumnsExists(self, csv):
        for col_idx in (COL_ImportStatus, COL_ImportMessage):
            csv.ensure_column_exists(col_idx=col_idx)

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Categories Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"  Shop:          {self.shop.name} [{self.shop.idx}]")
        self.info(f"Opening csv file: {self.file_path} ...")

        self.bev = CategoriesImportFromCsvEvent(file_path=self.file_path, shop=self.shop.idx, is_ongoing_event=True)
        self.report = {"count_processed_rows": 0, "count_new": 0}
        try:
            csv = CategoriesCsv()
            self.configure_csv(csv)
            csv.load_file(self.file_path)
            self.ensureProcessColumnsExists(csv)
            self.import_categories(csv)

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
