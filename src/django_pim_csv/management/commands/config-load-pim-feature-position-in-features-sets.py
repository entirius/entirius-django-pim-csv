# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand, CommandError

from ...worker import ConfigFeaturesInFeaturesSetsImporter


class Command(BaseCommand):
    help = "Loading PIM pim feature with position in features sets from CSV file. Exits non-zero, importing nothing, when any row is rejected."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Remove feature-set pairs the CSV does not list, in the sets the CSV names",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be detached (with --prune) and which required overrides change; write nothing",
        )

    @bi_django_command_decorator
    def handle(self, *args, **options):
        worker = ConfigFeaturesInFeaturesSetsImporter(
            file_path=options["file_path"], prune=options["prune"], dry_run=options["dry_run"]
        )
        try:
            worker.start()
        except Exception as e:  # bievents' decorator would swallow a ValueError and exit 0
            raise CommandError(str(e)) from e
        self.report_required(worker.required_changes, options["dry_run"])
        if options["prune"]:
            self.report_detached(worker.detached, options["dry_run"])
        self.stdout.write(self.style.SUCCESS("dry run, nothing written" if options["dry_run"] else "done"))

    def report_detached(self, detached, dry_run):
        for link in detached:
            self.stdout.write(f"  - {link}")
        verb = "Would detach" if dry_run else "Detached"
        self.stdout.write(f"{verb} {len(detached)} feature(s) from sets")

    def report_required(self, changes, dry_run):
        for change in changes:
            self.stdout.write(f"  - {change}")
        verb = "Would change" if dry_run else "Changed"
        if changes:
            self.stdout.write(f"{verb} {len(changes)} required override(s)")
