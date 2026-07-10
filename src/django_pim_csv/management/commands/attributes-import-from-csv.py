# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import sys

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django_pim.models import Feature

from ...worker import AttributesImporter

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Import attributes from csv"

    def add_arguments(self, parser):
        parser.add_argument("feature_idx", type=str)
        parser.add_argument("file_path", type=str)
        parser.add_argument("--limit", type=int, help="Limit importing csv rows")
        parser.add_argument(
            "-u", "--update-only", action="store_true", help="Do not add attributes, update existing only"
        )
        parser.add_argument(
            "--delete_not_in_csv", action="store_true", help="Delete attributes not in csv", default=False
        )
        Feature.objects.availability_table(print_out=True)
        print("")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        file_path = options["file_path"]
        feature_idx = options["feature_idx"]
        update_only = options["update_only"]
        delete_not_in_csv = options["delete_not_in_csv"]
        limit = options["limit"]
        try:
            Feature.objects.get(idx=feature_idx)
        except:
            logger.error(f"No feature with idx: {feature_idx} in database")
            self.stdout.write(self.style.ERROR(f"No feature with idx: {feature_idx} in database"))
            sys.exit(0)
        worker = AttributesImporter(file_path=file_path, feature_idx=feature_idx)
        worker.set_update_only(update_only)
        worker.set_limit(limit)
        worker.set_delete_not_in_csv(delete_not_in_csv)
        rv = worker.start()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
