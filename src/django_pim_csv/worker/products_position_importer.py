# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_pim.models import ProductInCategory, Shop, normalize_sku

from ..csv.products_position import COL_CATEGORY, COL_POSITION, COL_SKU, ProductsPositionCsv
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ProductsPositionImporter(AbstractSync):
    def __init__(self, file_path: str, shop_id: int | None = None, shop_idx: str | None = None):
        super().__init__()

        params_quantity = len({id(shop_id), id(shop_idx)} - {id(None)})
        if params_quantity != 1:
            raise ValueError("Exactly one of: shop_id or shop_idx must be set")
        if shop_id is not None:
            self.shop = Shop.objects.get(id=shop_id)
        elif shop_idx is not None:
            self.shop = Shop.objects.get(idx=shop_idx)
        else:
            raise Exception("should not happened")
        self.file_path = file_path

    def import_products_position(self, csv):
        self.info("Importing Products Position in Categories:")
        total = csv.get_max_rows()
        processed_nr = 0
        row_nr = 0
        for row in csv:
            row_nr += 1
            processed_nr += 1
            self.print_progress(processed_nr, total, "products")
            if self.limit and self.limit < processed_nr:
                self.info(f"There is row limit set to: {self.limit}")
                break
            try:
                sku = csv.get_row_value(row, COL_SKU)
                if not sku:
                    return
                sku = normalize_sku(sku)
                category_idx = csv.get_row_value(row, COL_CATEGORY)
                if not category_idx:
                    raise Exception(f"Product sku='{sku}' does not have category data in csv")

                position = csv.get_row_value(row, COL_POSITION)
                if not position or int(position) < 0:
                    position = 0
                else:
                    position = int(position)
                pic_object: ProductInCategory = ProductInCategory.objects.get(
                    product__real_product__sku__iexact=sku, product__shop=self.shop, category__idx=category_idx
                )
                pic_object.position = position
                pic_object.save()
                print(".", end="", flush=True)
            except ObjectDoesNotExist:
                logger.error(f"Cannot find matching: {self.shop.idx}, {sku}, {category_idx} row nr={row_nr} row={row}")
                # logger.error("Error while importing row nr={}, e={}".format(row_nr, e))
                # logger.exception(e)
                print("E", end="", flush=True)
            except Exception as e:
                logger.error(f"Error while importing row nr={row_nr}, e={e}")
                logger.exception(e)
                print("E", end="", flush=True)
        if processed_nr == 0:
            print("No products found\n")
        else:
            print("\ndone\n")

    def start(self):
        utc_tz = pytz.timezone("UTC")
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("============================================================")
        self.info(f"Products Position Import from csv started at {now_warsaw} [Warsaw TZ] ...")
        self.info(f"  Shop:          {self.shop.name} [{self.shop.idx}]")
        self.info(f"Opening csv file: {self.file_path} ...")

        csv = ProductsPositionCsv()
        csv.load_file(self.file_path)
        self.import_products_position(csv)

        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("Packages Import from csv is done at {} [Warsaw TZ]".format(now_warsaw.strftime("%Y-%m-%d %H:%M:%S")))

        return True
