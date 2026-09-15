# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import os
import sys

from django.db import transaction
from django.utils import timezone
from django_pim.models import FeatureInFeatureSet, Shop
from lockfile import LockFile

from django_pim_csv import settings

from ..settings import SKIP_FILES_DEFAULT, SKIP_LINKING_PRODUCTS_DEFAULT, SKIP_PICTURES_DEFAULT

logger = logging.getLogger("django")


class ImportRowsError(Exception):
    """Rows were rejected; the whole import has been rolled back."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} row(s) rejected, nothing imported:\n" + "\n".join(errors))


class AbstractSync:
    LOCK_FILE = f"/tmp/_lock_{settings.BI_BUSINESS_UNIT}_csv_import.tmp"
    lock = None
    limit = None  # int or None liczy sie razem z headerem, --limit
    lock_file = True
    fail_if_locked = False  # True: a held lock exits 1 instead of 0
    prune = False  # --prune, used by load_atomically
    dry_run = False  # --dry-run, used by load_atomically
    errors = None
    detached = None
    kept_links = None  # {feature_set_pk: {feature_pk}} named by the CSV
    skip_pictures = SKIP_PICTURES_DEFAULT  # --skip-pictures
    skip_files = SKIP_FILES_DEFAULT  # --skip-files
    skip_linking = SKIP_LINKING_PRODUCTS_DEFAULT  # --skip-linking
    update_only = False  # --update-only
    delete = False  # --delete
    delete_attr = True  # --delete-attr
    update_translations_only = False  # --update-translations-only
    langs = None  # iso2 lang ids
    shop = None

    def __init__(self):
        if self.lock_file:
            self.lock = LockFile(self.LOCK_FILE, wait_for_acquire=False)
            try:
                self.lock.acquire()
            except OSError:
                # another instance is running
                now = timezone.now()
                m = f"[{now}] Exiting, another instance is running ..."
                print(m)
                logger.info(m)
                sys.exit(1 if self.fail_if_locked else 0)
        self.ensure_dir_exists(settings.TMP_DIR)
        self.init_langs()

    def init_langs(self):
        self.langs = [settings.T9N_DEFAULT_LANG]
        for shop in Shop.objects.all():
            for l in shop.languages.all().values_list("iso2", flat=True):
                if l not in self.langs:
                    self.langs.append(l)

    def configure_column_text_t9n(self, csv, idx):
        for lang in self.langs:
            shop_default_lang = getattr(getattr(getattr(self, "shop", None), "default_language", None), "iso2", None)
            default_lang = (
                shop_default_lang
                if settings.IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM and shop_default_lang
                else settings.T9N_DEFAULT_LANG
            )
            is_required = True if lang == default_lang else False
            col_idx = self.generate_feature_col_idx(idx, lang)
            csv.add_col_config(col_idx=col_idx, is_required=is_required)
            self.info("  - {:28} col_idx = {:32} is_required = {}".format(idx, '"' + col_idx + '"', is_required))

    def load_atomically(self, csv):
        """Run load_data (and prune) in one transaction; roll back on any row error or dry run."""
        self.errors, self.detached, self.kept_links = [], [], {}
        with transaction.atomic():
            self.load_data(csv)
            if self.prune:
                self.prune_links()
            if self.errors or self.dry_run:
                transaction.set_rollback(True)
        if self.errors:
            raise ImportRowsError(self.errors)

    def row_error(self, row_nr, reason):
        self.errors.append(f"row {row_nr}: {reason}")
        self.error(f"row {row_nr}: {reason}")

    def keep_links(self, feature_set, features):
        self.kept_links.setdefault(feature_set.pk, set()).update(feature.pk for feature in features)

    def prune_links(self):
        """Delete memberships of the CSV's sets that the CSV does not list, recording each as 'set: feature'."""
        for feature_set_pk, feature_pks in self.kept_links.items():
            stale = FeatureInFeatureSet.objects.filter(feature_set_id=feature_set_pk).exclude(
                feature_id__in=feature_pks
            )
            for set_idx, feature_idx in stale.values_list("feature_set__idx", "feature__idx"):
                self.detached.append(f"{set_idx}: {feature_idx}")
            stale.delete()

    def info(self, msg):
        print(msg, flush=True)
        logger.info(msg)

    def error(self, msg):
        print(f"ERROR: {msg}", flush=True)
        logger.error(msg)

    def ensure_dir_exists(self, path_dir):
        if os.path.isdir(path_dir):
            return True
        logger.info(f'"{path_dir}" directory does not exists, creating')
        os.makedirs(path_dir)

    def set_skip_pictures(self, skip_pictures):
        self.skip_pictures = bool(skip_pictures)
        if self.skip_pictures:
            logger.info(f"Import will skip pictures import, skip_pictures is set to: {self.skip_pictures}")

    def set_skip_files(self, skip_files):
        self.skip_files = bool(skip_files)
        if self.skip_files:
            logger.info(f"Import will skip files import, skip_files is set to: {self.skip_pictures}")

    def set_skip_linking(self, skip_linking):
        self.skip_linking = bool(skip_linking)
        if self.skip_linking:
            logger.info(f"Import will skip products linking, skip_linking is set to: {self.skip_linking}")

    def set_limit(self, limit):
        if limit is None:
            return
        self.limit = int(limit)
        logger.info(f"Import will limit import to first {self.limit} rows")

    def set_delete_not_in_csv(self, delete_not_in_csv):
        self.delete = bool(delete_not_in_csv)
        if self.delete:
            logger.info(f"Import will delete objects not in csv, delete_not_in_csv is set to: {self.delete}")

    def set_update_only(self, update_only):
        self.update_only = bool(update_only)
        if self.update_only:
            logger.info("Import will do updates only")

    def set_delete_attr(self, delete_attr):
        self.delete_attr = bool(delete_attr)
        if self.delete_attr:
            logger.info("Import will do delete only csv feature")

    def set_delete(self, delete):
        self.delete = bool(delete)
        if self.delete:
            logger.info("It is full import, and will delete not existing objects")

    def set_update_translations_only(self, update_only):
        self.update_translations_only = bool(update_only)
        if self.update_translations_only:
            self.set_update_only(True)
            logger.info("Import will do translations updates only")

    def generate_feature_col_idx(self, idx, lang=None):
        if lang is None:
            return f"{idx}"
        return f"{idx} {lang}"

    def print_progress(self, cnt, total, msg, every=100):
        if cnt % every == 0:
            msg = f"  - {cnt} / {total} {msg}"
            self.info(msg)
