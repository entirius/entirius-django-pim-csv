# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Product linking: the link type columns must land on the ProductLink FK."""

import pytest
from django_pim.models import Channel, FeatureSet, Product, ProductLink, RealProduct
from django_regional.models import Currency, Language

from django_pim_csv.csv.products import ProductsCsv
from django_pim_csv.worker.products_importer import ProductsImporter

CHANNEL_IDX = "novatrade"
CSV_HEADER = "sku,linked cross sell,linked unknown\n"


@pytest.fixture
def channel(db):
    language, _ = Language.objects.get_or_create(
        iso2="en", defaults={"iso3": "eng", "name_en": "English", "name_pl": "angielski"}
    )
    currency, _ = Currency.objects.get_or_create(iso3="EUR", defaults={"name_en": "Euro", "name_pl": "euro"})
    channel = Channel.objects.create(
        idx=CHANNEL_IDX, name="Novatrade", default_language=language, default_currency=currency
    )
    channel.languages.add(language)
    return channel


@pytest.fixture
def products(channel):
    feature_set = FeatureSet.objects.create(idx="default", name="Default", is_default=True)
    created = {}
    for sku in ("ENT-001", "ENT-002", "ENT-003"):
        real_product = RealProduct.objects.create(sku=sku)
        created[sku] = Product.objects.create(real_product=real_product, shop=channel, feature_set=feature_set)
    return created


def load_csv(tmp_path, rows):
    file_path = tmp_path / "products.csv"
    file_path.write_text(CSV_HEADER + "".join(f"{sku},{cross_sell},{unknown}\n" for sku, cross_sell, unknown in rows))
    csv = ProductsCsv()
    csv.load_file(str(file_path))
    return str(file_path), csv


@pytest.mark.django_db
def test_link_products_resolves_link_type_to_a_link_type_record(tmp_path, products):
    """A named link column links through the ProductLinkType row of the same name."""
    file_path, csv = load_csv(tmp_path, [("ENT-001", "ENT-002", "")])
    importer = ProductsImporter(file_path=file_path, shop_idx=CHANNEL_IDX)

    importer.link_products(csv)

    link = ProductLink.objects.get(product=products["ENT-001"], linked_product=products["ENT-002"])
    assert link.link_type.idx == "crosssell"


@pytest.mark.django_db
def test_link_products_leaves_unknown_links_without_a_link_type(tmp_path, products):
    """The unknown column has no ProductLinkType row — the link is stored untyped."""
    file_path, csv = load_csv(tmp_path, [("ENT-001", "", "ENT-003")])
    importer = ProductsImporter(file_path=file_path, shop_idx=CHANNEL_IDX)

    importer.link_products(csv)

    link = ProductLink.objects.get(product=products["ENT-001"], linked_product=products["ENT-003"])
    assert link.link_type is None
