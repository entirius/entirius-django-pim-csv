# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import sys

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django_pim.models import Shop

from ...worker import ProductAttributeImagesImporter

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Import product attrbiute images from csv"

    def add_arguments(self, parser):
        parser.add_argument("shop_idx", type=str)
        parser.add_argument("file_path", type=str)
        Shop.objects.availability_table(print_out=True)
        print("")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        file_path = options["file_path"]
        shop_idx = options["shop_idx"]
        try:
            Shop.objects.get(idx=shop_idx)
        except Shop.DoesNotExist:
            logger.error(f"No shop with idx: {shop_idx} in database")
            self.stdout.write(self.style.ERROR(f"No shop with idx: {shop_idx} in database"))
            sys.exit(0)
        worker = ProductAttributeImagesImporter(file_path=file_path, shop_idx=shop_idx)

        rv = worker.start()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
