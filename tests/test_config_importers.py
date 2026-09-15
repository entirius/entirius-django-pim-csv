# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""config-load-pim-features / -features-sets / -feature-position-in-features-sets: exit codes, rollback, prune."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django_pim.models import Feature, FeatureInFeatureSet, FeatureScopeEnum, FeatureSet
from lockfile import LockFile

from django_pim_csv.worker.abstract import AbstractSync

FEATURES_HEADER = "idx,scope,type,name en,filterable,searchable\n"
SETS_HEADER = "idx,name,desc,is-default,features\n"
POSITIONS_HEADER = "feature-idx,feature-set-idx,position\n"


def run(command, *args):
    out = io.StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def links(feature_set_idx):
    rows = FeatureInFeatureSet.objects.filter(feature_set__idx=feature_set_idx)
    return dict(rows.values_list("feature__idx", "position"))


@pytest.mark.django_db
class TestConfigLoadPimFeatures:
    command = "config-load-pim-features"

    def test_clean_import_succeeds(self, write_csv):
        path = write_csv(
            "f.csv", FEATURES_HEADER + "color,business_unit,text,Color,0,0\nsize,business_unit,text,Size,0,0\n"
        )

        run(self.command, path)

        assert set(Feature.objects.values_list("idx", flat=True)) >= {"color", "size"}

    def test_scope_mismatch_fails_and_writes_nothing(self, write_csv, make_feature):
        make_feature("color", scope=FeatureScopeEnum.BUSINESS_UNIT)
        path = write_csv("f.csv", FEATURES_HEADER + "size,business_unit,text,Size,0,0\ncolor,system,text,Color,0,0\n")

        with pytest.raises(CommandError, match="row 2"):
            run(self.command, path)

        assert not Feature.objects.filter(idx="size").exists()

    def test_unknown_type_fails(self, write_csv):
        path = write_csv("f.csv", FEATURES_HEADER + "color,business_unit,no-such-type,Color,0,0\n")

        with pytest.raises(CommandError, match="row 1"):
            run(self.command, path)

    def test_error_in_later_row_rolls_back_earlier_rows(self, write_csv):
        rows = "a1,business_unit,text,A1,0,0\na2,business_unit,text,A2,0,0\na3,business_unit,bad,A3,0,0\n"
        path = write_csv("f.csv", FEATURES_HEADER + rows)

        with pytest.raises(CommandError, match="row 3"):
            run(self.command, path)

        assert not Feature.objects.filter(idx__in=["a1", "a2"]).exists()

    def test_held_lock_keeps_exit_zero_for_other_importers(self, lock_file_path):
        holder = LockFile(lock_file_path)
        holder.acquire()

        with pytest.raises(SystemExit) as exc:
            AbstractSync()

        assert exc.value.code == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "command",
    ["config-load-pim-features", "config-load-pim-features-sets", "config-load-pim-feature-position-in-features-sets"],
)
def test_held_lock_exits_non_zero(command, write_csv, lock_file_path):
    path = write_csv("any.csv", "idx\n")
    holder = LockFile(lock_file_path)
    holder.acquire()

    with pytest.raises(SystemExit) as exc:
        run(command, path)

    assert exc.value.code != 0


@pytest.mark.django_db
class TestConfigLoadPimFeaturesSets:
    command = "config-load-pim-features-sets"

    def test_unknown_feature_fails_and_writes_nothing(self, write_csv, make_feature):
        make_feature("color")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"color,ghost"\n')

        with pytest.raises(CommandError, match="ghost"):
            run(self.command, path)

        assert not FeatureSet.objects.filter(idx="shoes").exists()

    def test_feature_idx_is_normalized(self, write_csv, make_feature):
        make_feature("color")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"Color"\n')

        run(self.command, path)

        assert set(links("shoes")) == {"color"}

    def test_without_prune_import_only_adds(self, write_csv, make_feature, make_set, link):
        shoes = make_set("shoes")
        link(shoes, make_feature("legacy"))
        make_feature("color")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"color"\n')

        run(self.command, path)

        assert set(links("shoes")) == {"legacy", "color"}

    def test_prune_detaches_features_missing_from_csv(self, write_csv, make_feature, make_set, link):
        shoes, hats = make_set("shoes"), make_set("hats")
        legacy = make_feature("legacy")
        link(shoes, legacy)
        link(hats, legacy)
        make_feature("color")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"color"\n')

        out = run(self.command, path, "--prune")

        assert set(links("shoes")) == {"color"}
        assert set(links("hats")) == {"legacy"}
        assert "shoes: legacy" in out

    def test_prune_dry_run_lists_and_writes_nothing(self, write_csv, make_feature, make_set, link):
        shoes = make_set("shoes")
        link(shoes, make_feature("legacy"))
        make_feature("color")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"color"\n')

        out = run(self.command, path, "--prune", "--dry-run")

        assert set(links("shoes")) == {"legacy"}
        assert "shoes: legacy" in out
        assert "Would detach 1" in out

    def test_invalid_set_idx_fails(self, write_csv):
        path = write_csv("s.csv", SETS_HEADER + "!!!,Broken,,0,\n")

        with pytest.raises(CommandError, match="row 1"):
            run(self.command, path)

    def test_prune_keeps_features_of_a_set_listed_twice(self, write_csv, make_feature):
        make_feature("color")
        make_feature("size")
        path = write_csv("s.csv", SETS_HEADER + 'shoes,Shoes,,0,"color"\nshoes,Shoes,,0,"size"\n')

        run(self.command, path, "--prune")

        assert set(links("shoes")) == {"color", "size"}

    def test_prune_empties_a_set_listed_without_features(self, write_csv, make_feature, make_set, link):
        link(make_set("shoes"), make_feature("legacy"))
        path = write_csv("s.csv", SETS_HEADER + "shoes,Shoes,,0,\n")

        run(self.command, path, "--prune")

        assert links("shoes") == {}

    def test_dry_run_requires_prune(self, write_csv):
        path = write_csv("s.csv", SETS_HEADER)

        with pytest.raises(CommandError, match="--prune"):
            run(self.command, path, "--dry-run")


@pytest.mark.django_db
class TestConfigLoadPimFeaturePositions:
    command = "config-load-pim-feature-position-in-features-sets"

    def test_unknown_feature_fails_and_writes_nothing(self, write_csv, make_feature, make_set):
        make_set("shoes")
        make_feature("color")
        path = write_csv("p.csv", POSITIONS_HEADER + "color,shoes,10\nghost,shoes,20\n")

        with pytest.raises(CommandError, match="row 2"):
            run(self.command, path)

        assert links("shoes") == {}

    @pytest.mark.parametrize("bad_row", ["color,shoes,abc", "color,shoes,99999999999", ",shoes,10"])
    def test_invalid_row_fails_and_writes_nothing(self, bad_row, write_csv, make_feature, make_set):
        make_set("shoes")
        make_feature("color")
        path = write_csv("p.csv", POSITIONS_HEADER + bad_row + "\n")

        with pytest.raises(CommandError, match="row 1"):
            run(self.command, path)

        assert links("shoes") == {}

    def test_import_sets_positions(self, write_csv, make_feature, make_set, link):
        shoes = make_set("shoes")
        link(shoes, make_feature("color"), position=5)
        path = write_csv("p.csv", POSITIONS_HEADER + "color,shoes,10\n")

        run(self.command, path)

        assert links("shoes") == {"color": 10}

    def test_prune_removes_pairs_missing_from_csv(self, write_csv, make_feature, make_set, link):
        shoes, hats = make_set("shoes"), make_set("hats")
        color, legacy = make_feature("color"), make_feature("legacy")
        link(shoes, color)
        link(shoes, legacy)
        link(hats, legacy)
        path = write_csv("p.csv", POSITIONS_HEADER + "color,shoes,10\n")

        run(self.command, path, "--prune")

        assert links("shoes") == {"color": 10}
        assert links("hats") == {"legacy": 0}

    def test_prune_dry_run_writes_nothing(self, write_csv, make_feature, make_set, link):
        shoes = make_set("shoes")
        link(shoes, make_feature("color"), position=5)
        link(shoes, make_feature("legacy"))
        path = write_csv("p.csv", POSITIONS_HEADER + "color,shoes,10\n")

        out = run(self.command, path, "--prune", "--dry-run")

        assert links("shoes") == {"color": 5, "legacy": 0}
        assert "Would detach 1" in out
