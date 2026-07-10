# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand

from ...worker import ConfigFeaturesInFeaturesSetsImporter


class Command(BaseCommand):
    help = "Loading PIM pim feature with position in features sets from CSV file."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    @bi_django_command_decorator
    def handle(self, *args, **options):
        file_path = options["file_path"]

        worker = ConfigFeaturesInFeaturesSetsImporter(file_path=file_path)
        rv = worker.start()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
