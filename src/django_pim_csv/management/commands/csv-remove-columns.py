# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import csv
import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Remove specified (by param) columns from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to the CSV file")
        parser.add_argument("exclude_column", type=str, help="Columns to exclude (comma-separated)")

    def handle(self, *args, **options):
        file_path = options["file_path"]
        exclude_column = options["exclude_column"].split(",")

        try:
            with open(file_path) as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = [field for field in reader.fieldnames if field not in exclude_column]

                output_rows = []
                for row in reader:
                    output_rows.append({fieldname: row[fieldname] for fieldname in fieldnames})

            formatted_epoch = int(time.time())
            new_file_path = file_path.replace(".csv", f"_removed_col_{formatted_epoch}.csv")

            with open(new_file_path, "w", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(output_rows)

            self.stdout.write(self.style.SUCCESS(f"Successfully removed columns and saved results to {new_file_path}"))
        except FileNotFoundError:
            raise CommandError(f"File not found: {file_path}")
        except Exception as e:
            raise CommandError(f"An error occurred: {str(e)}")
