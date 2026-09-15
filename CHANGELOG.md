# Changelog

## 4.0.0 — 2026-09-15

- **Breaking:** `config-load-pim-features`, `config-load-pim-features-sets` and
  `config-load-pim-feature-position-in-features-sets` run in one transaction and exit
  non-zero when any row is rejected (unknown feature idx or type, scope change, bad position,
  database error), listing every rejected row; nothing is written. They used to skip such rows
  and exit 0. A held import lock also exits non-zero for these three commands.
- `--prune` on the feature-sets and positions commands makes the memberships of the sets named
  in the CSV equal to the CSV; `--dry-run` lists what would be detached. Without `--prune` both
  stay additive.
- The feature-sets command normalizes feature idx values like the other importers.
- **Breaking:** `attributes-import-from-csv` no longer deletes attributes missing from the CSV
  unless `DELETE_ATTRIBUTES_NOT_IN_CSV` or `--delete_not_in_csv` is set; the keep-list compares
  normalized idx values, so listed attributes are never deleted.
- Product links are saved through the `link_type` foreign key; imports with links no longer fail
  on save.
- Tests run against PostgreSQL (`DATABASE_URL`).

## 3.0.0 — 2026-07-10

- Initial public release: the CSV import pipeline for PIM — products,
  categories, attributes, and features via management commands with a
  documented CSV format.
- Migrations squashed into a single initial migration for the Entirius epoch.
