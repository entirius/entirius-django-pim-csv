# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import sys
import time
from argparse import BooleanOptionalAction

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django_pim.models import Shop

from ...worker import ProductsImporter

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Import products from csv"

    def add_arguments(self, parser):
        parser.add_argument("shop_idx", type=str)
        parser.add_argument("file_path", type=str)
        parser.add_argument("-s", "--skip-pictures", action="store_true", help="Do not import pictures")
        parser.add_argument("-d", "--skip-files", action="store_true", help="Do not import files")
        parser.add_argument("--limit", type=int, help="Limit importing csv rows")
        parser.add_argument(
            "-u", "--update-only", action="store_true", help="Do not add products, update existing only"
        )
        parser.add_argument(
            "--update-translations-only", action="store_true", help="Update translations on existing products only"
        )
        parser.add_argument(
            "-da",
            "--delete-attr",
            action=BooleanOptionalAction,
            help="Delete attribute from product if not in csv",
            default=True,
        )
        parser.add_argument("--skip-linking", action="store_true", help="Skip linking products?")
        Shop.objects.availability_table(print_out=True)
        print("")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        time_start = time.time()
        file_path = options["file_path"]
        shop_idx = options["shop_idx"]
        skip_pictures = options["skip_pictures"]
        skip_files = options["skip_files"]
        skip_linking = options["skip_linking"]
        update_only = options["update_only"]
        delete_attr = options["delete_attr"]
        update_translations_only = options["update_translations_only"]
        limit = options["limit"]
        try:
            Shop.objects.get(idx=shop_idx)
        except:
            logger.error(f"No shop with idx: {shop_idx} in database")
            self.stdout.write(self.style.ERROR(f"No shop with idx: {shop_idx} in database"))
            sys.exit(0)
        worker = ProductsImporter(file_path=file_path, shop_idx=shop_idx)
        if skip_pictures:
            worker.set_skip_pictures(skip_pictures)
        if skip_files:
            worker.set_skip_files(skip_files)
        if skip_linking:
            worker.set_skip_linking(skip_linking)
        worker.set_update_only(update_only)
        worker.set_delete_attr(delete_attr)
        worker.set_update_translations_only(update_translations_only)
        worker.set_limit(limit)
        rv = worker.start()
        time_end = time.time()

        if rv:
            self.stdout.write(self.style.SUCCESS(f"done. Took {time_end - time_start:.2f} seconds"))
        else:
            self.stdout.write(self.style.ERROR(f"error. Took {time_end - time_start:.2f} seconds"))
