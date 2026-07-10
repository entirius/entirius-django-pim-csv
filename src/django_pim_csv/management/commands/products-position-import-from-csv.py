# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import sys

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django_pim.models import Shop

from ...worker import ProductsPositionImporter

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Import products position in category from csv"

    def add_arguments(self, parser):
        parser.add_argument("shop_idx", type=str)
        parser.add_argument("file_path", type=str)
        parser.add_argument("--limit", type=int, help="Limit importing csv rows")
        Shop.objects.availability_table(print_out=True)
        print("")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        shop_idx = options["shop_idx"]
        file_path = options["file_path"]

        limit = options["limit"]
        try:
            Shop.objects.get(idx=shop_idx)
        except:
            logger.error(f"No shop with idx: {shop_idx} in database")
            self.stdout.write(self.style.ERROR(f"No shop with idx: {shop_idx} in database"))
            sys.exit(0)
        worker = ProductsPositionImporter(file_path=file_path, shop_idx=shop_idx)
        worker.set_limit(limit)
        rv = worker.start()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
