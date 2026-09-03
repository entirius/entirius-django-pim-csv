# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared fixtures for the importer tests."""

import pytest

from django_pim_csv.worker.abstract import AbstractSync


@pytest.fixture(autouse=True)
def _no_import_lock(monkeypatch):
    """Drop the cross-process import lock.

    Importers flock `/tmp/_lock_{BI_BUSINESS_UNIT}_csv_import.tmp` and `sys.exit(0)` when the
    lock is taken. Two importers alive in one pytest process would collide on it and kill the
    whole run instead of failing a test.
    """
    monkeypatch.setattr(AbstractSync, "lock_file", False)
