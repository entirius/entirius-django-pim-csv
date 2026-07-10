# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django_pim.models import Feature

from ...worker import CustomModifiersAttributesImporter

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Import custom modifiers attributes from csv"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--shop_idx", type=str)
        parser.add_argument("--limit", type=int, help="Limit importing csv rows")
        parser.add_argument(
            "-u", "--update-only", action="store_true", help="Do not add attributes, update existing only"
        )
        Feature.objects.availability_table(print_out=True)
        print("")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        file_path = options["file_path"]
        shop_idx = options["shop_idx"]
        update_only = options["update_only"]
        limit = options["limit"]

        worker = CustomModifiersAttributesImporter(file_path=file_path, shop_idx=shop_idx)
        worker.set_update_only(update_only)
        worker.set_limit(limit)
        rv = worker.start()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
