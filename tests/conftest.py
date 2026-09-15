# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared fixtures for the importer tests."""

import pytest
from django_pim.models import Feature, FeatureInFeatureSet, FeatureScopeEnum, FeatureSet, FeatureTypeEnum

from django_pim_csv.worker.abstract import AbstractSync


@pytest.fixture(autouse=True)
def _no_import_lock(monkeypatch):
    """Drop the cross-process import lock.

    Importers flock `/tmp/_lock_{BI_BUSINESS_UNIT}_csv_import.tmp` and `sys.exit(0)` when the
    lock is taken. Two importers alive in one pytest process would collide on it and kill the
    whole run instead of failing a test.
    """
    monkeypatch.setattr(AbstractSync, "lock_file", False)


@pytest.fixture
def lock_file_path(tmp_path, monkeypatch):
    """Re-enable the import lock on a per-test path, for tests about the lock itself."""
    path = str(tmp_path / "import.lock")
    monkeypatch.setattr(AbstractSync, "lock_file", True)
    monkeypatch.setattr(AbstractSync, "LOCK_FILE", path)
    return path


@pytest.fixture
def write_csv(tmp_path):
    def write(name, content):
        path = tmp_path / name
        path.write_text(content)
        return str(path)

    return write


@pytest.fixture
def make_feature(db):
    def make(idx, scope=FeatureScopeEnum.BUSINESS_UNIT):
        return Feature.objects.create(idx=idx, scope=scope, feature_type=FeatureTypeEnum.TEXT, name_t9n={"en": idx})

    return make


@pytest.fixture
def link(db):
    def make(feature_set, feature, position=0):
        return FeatureInFeatureSet.objects.create(feature_set=feature_set, feature=feature, position=position)

    return make


@pytest.fixture
def make_set(db):
    def make(idx):
        return FeatureSet.objects.create(idx=idx, name=idx, desc="")

    return make
