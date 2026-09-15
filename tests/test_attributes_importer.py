# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Attribute import: which attributes survive a run that does not list them."""

import pytest
from django_pim.models import Attribute, Feature, FeatureScopeEnum, FeatureTypeEnum

from django_pim_csv.worker import attributes_importer
from django_pim_csv.worker.attributes_importer import AttributesImporter

CSV_HEADER = "idx,name en\n"
FEATURE_IDX = "supplier"


def write_csv(tmp_path, rows):
    file_path = tmp_path / "attributes.csv"
    file_path.write_text(CSV_HEADER + "".join(f"{idx},{name}\n" for idx, name in rows))
    return str(file_path)


@pytest.fixture
def name_feature(db):
    return Feature.objects.create(
        idx="name",
        scope=FeatureScopeEnum.SYSTEM,
        feature_type=FeatureTypeEnum.VARCHAR255_T9N,
        name_t9n={"en": "Name"},
        display_order=1,
    )


@pytest.fixture
def supplier_feature(db):
    return Feature.objects.create(idx=FEATURE_IDX, name_t9n={"en": "Supplier"}, display_order=2)


@pytest.mark.django_db
def test_import_keeps_attributes_missing_from_csv(tmp_path, name_feature, supplier_feature):
    """A partial CSV must not wipe the rest of the feature's attributes."""
    Attribute.objects.create(feature=supplier_feature, idx="kestrel-supply", name_t9n={"en": "Kestrel Supply"})
    file_path = write_csv(tmp_path, [("novatrade", "Novatrade")])

    AttributesImporter(file_path=file_path, feature_idx=FEATURE_IDX).start()

    idx_list = set(Attribute.objects.filter(feature=supplier_feature).values_list("idx", flat=True))
    assert idx_list == {"kestrel-supply", "novatrade"}


@pytest.mark.django_db
def test_setting_deletes_attributes_missing_from_csv(monkeypatch, tmp_path, name_feature, supplier_feature):
    """DELETE_ATTRIBUTES_NOT_IN_CSV opts a deployment back into full-sync deletes."""
    monkeypatch.setattr(attributes_importer, "DELETE_ATTRIBUTES_NOT_IN_CSV", True)
    Attribute.objects.create(feature=supplier_feature, idx="kestrel-supply", name_t9n={"en": "Kestrel Supply"})
    file_path = write_csv(tmp_path, [("novatrade", "Novatrade")])

    AttributesImporter(file_path=file_path, feature_idx=FEATURE_IDX).start()

    idx_list = list(Attribute.objects.filter(feature=supplier_feature).values_list("idx", flat=True))
    assert idx_list == ["novatrade"]


@pytest.mark.django_db
def test_delete_keeps_attributes_whose_csv_idx_needs_normalization(tmp_path, name_feature, supplier_feature):
    """Rows are stored under a normalized idx, so the delete pass must compare normalized values."""
    Attribute.objects.create(feature=supplier_feature, idx="novatrade", name_t9n={"en": "Novatrade"})
    file_path = write_csv(tmp_path, [("Kestrel Supply", "Kestrel Supply")])
    importer = AttributesImporter(file_path=file_path, feature_idx=FEATURE_IDX)
    importer.set_delete_not_in_csv(True)

    importer.start()

    idx_list = list(Attribute.objects.filter(feature=supplier_feature).values_list("idx", flat=True))
    assert idx_list == ["kestrel-supply"]
