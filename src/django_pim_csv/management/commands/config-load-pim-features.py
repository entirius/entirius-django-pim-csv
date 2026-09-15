# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand, CommandError

from ...worker import ConfigFeaturesImporter


class Command(BaseCommand):
    help = "Loading PIM configuration from CSV file. Exits non-zero, importing nothing, when any row is rejected."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    @bi_django_command_decorator
    def handle(self, *args, **options):
        worker = ConfigFeaturesImporter(file_path=options["file_path"])
        try:
            worker.start()
        except Exception as e:  # bievents' decorator would swallow a ValueError and exit 0
            raise CommandError(str(e)) from e
        self.stdout.write(self.style.SUCCESS("done"))
