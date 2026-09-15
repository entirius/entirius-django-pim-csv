# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand, CommandError

from ...worker import ConfigFeaturesSetsImporter


class Command(BaseCommand):
    help = "Loading PIM configuration from CSV file. Exits non-zero, importing nothing, when any row is rejected."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument(
            "--prune", action="store_true", help="Detach features the CSV does not list, in the sets the CSV names"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="With --prune: list what would be detached, write nothing"
        )

    @bi_django_command_decorator
    def handle(self, *args, **options):
        if options["dry_run"] and not options["prune"]:
            raise CommandError("--dry-run requires --prune")
        worker = ConfigFeaturesSetsImporter(
            file_path=options["file_path"], prune=options["prune"], dry_run=options["dry_run"]
        )
        try:
            worker.start()
        except Exception as e:  # bievents' decorator would swallow a ValueError and exit 0
            raise CommandError(str(e)) from e
        self.report_detached(worker.detached, options["dry_run"])
        self.stdout.write(self.style.SUCCESS("dry run, nothing written" if options["dry_run"] else "done"))

    def report_detached(self, detached, dry_run):
        for link in detached:
            self.stdout.write(f"  - {link}")
        verb = "Would detach" if dry_run else "Detached"
        self.stdout.write(f"{verb} {len(detached)} feature(s) from sets")
