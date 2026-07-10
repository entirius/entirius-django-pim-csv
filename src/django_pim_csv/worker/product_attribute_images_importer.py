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
from django_pim.models import (
    Attribute,
    Product,
    ProductAttributeCustomImage,
    ProductAttributeImage,
    Shop,
    normalize_sku,
)

from ..csv.product_attribute_images import (
    COL_COLOR_HASH,
    COL_IDX,
    COL_IMAGES,
    COL_SKU,
    IMAGES_SEPARATOR,
    ProductAttributeImagesCsv,
)
from .abstract import AbstractSync

logger = logging.getLogger("django")


class ProductAttributeImagesImporter(AbstractSync):
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

    def import_images(self, path, raport, product, attribute, color_hash):
        if not path:
            picture = None
        elif path[:7] == "http://" or path[:8] == "https://" or path[:6] == "ftp://":
            path = path.strip()
            url = path
            try:
                validate = URLValidator()
                validate(url)
            except ValidationError:
                logger.warning(f"Ignoring invalid picture url: {url}")
                raport["images_processed_error"] += 1
                return
            picture, is_downloaded = PictureManager.download_picture(url)
        else:
            path = path.strip()
            if path[0] == "/":
                full_path = path
            else:
                full_path = os.path.join(os.path.dirname(self.file_path), path)
            if not os.path.exists(full_path):
                logger.error(f'Can not import not existing picture path="{full_path}"')
                raport["images_processed_error"] += 1
                return
            try:
                # tutaj nastepuje validacja, nalezy kontynuowac przy nieprawidlowych zdjeciach
                picture = PictureManager.get_picture(full_path)
            except Exception as e:
                logger.error(f"Error while loading picture path={path}, e={e}")
                raport["images_processed_error"] += 1
                return
        try:
            if product:
                productpic, created = ProductAttributeImage.objects.update_or_create(
                    product=product, attribute=attribute, defaults={"color_hash": color_hash, "picture": picture}
                )
            else:
                productpic, created = ProductAttributeImage.objects.update_or_create(
                    product=product, attribute=attribute, defaults={"color_hash": color_hash, "picture": picture}
                )
        except Exception as e:
            logger.error(f"Error while importing picture path={path}, e={e}")
            raport["images_processed_error"] += 1
            return

        raport["images_processed_ok"] += 1

    def import_product_attribute_images(self, csv):
        self.info("Importing product attribute images ...")
        total = csv.get_max_rows()
        processed_nr = 0
        row_nr = 0
        raport = {"images_processed_ok": 0, "images_processed_error": 0}
        for row in csv:
            row_nr += 1
            processed_nr += 1
            self.print_progress(processed_nr, total, "product_attribute_images")
            if self.limit and self.limit < processed_nr:
                self.info(f"There is row limit set to: {self.limit}")
                break
            try:
                sku = csv.get_row_value(row, COL_SKU)
                if sku:
                    sku = normalize_sku(sku)
                attribute_idx = csv.get_row_value(row, COL_IDX)
                if not attribute_idx:
                    logger.error(f"Product sku='{sku}' does not have attribute data in csv")
                    print("E", end="", flush=True)
                    continue

                images_values = csv.get_row_value(row, COL_IMAGES)
                color_hash = csv.get_row_value(row, COL_COLOR_HASH)
                paths = []

                if images_values:
                    for img_value in images_values.split(IMAGES_SEPARATOR):
                        img_value = img_value.strip()
                        if img_value:
                            paths.append((img_value, color_hash))
                elif color_hash:
                    paths.append((None, color_hash))
                try:
                    product = Product.objects.get(real_product__sku=sku, shop=self.shop) if sku else None
                    attribute = Attribute.objects.get(idx=attribute_idx)
                except Product.DoesNotExist:
                    logger.error(f"Cannot find product with sku: {sku} in shop: {self.shop.idx}")
                    print("E", end="", flush=True)
                    continue
                except Attribute.DoesNotExist:
                    logger.error(f"Cannot find attribute with idx: {attribute_idx}")
                    print("E", end="", flush=True)
                    continue

                ProductAttributeCustomImage.objects.filter(product=product).delete()

                for path in paths:
                    try:
                        self.import_images(path[0], raport, product, attribute, path[1])
                    except Exception as e:
                        logger.error(f"Error while importing row nr={row_nr}, e={e}")
                        logger.exception(e)
                        print("E", end="", flush=True)

                print(".", end="", flush=True)
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

        csv = ProductAttributeImagesCsv()
        csv.load_file(self.file_path)
        self.import_product_attribute_images(csv)

        now = timezone.now().replace(tzinfo=utc_tz)
        now_warsaw = now.astimezone(warsaw_tz)
        self.info("Packages Import from csv is done at {} [Warsaw TZ]".format(now_warsaw.strftime("%Y-%m-%d %H:%M:%S")))

        return True
