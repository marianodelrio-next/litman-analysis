from __future__ import annotations

from litman_harness.dossier.membership import belongs_to_root, in_litman
from litman_harness.dossier.models import FOLDER_MIME, Resource
from litman_harness.errors import HarnessError


class Drive:
    def __init__(self, *resources: Resource):
        self.resources = {item.id: item for item in resources}
        self.requested: list[str] = []

    def get(self, file_id):
        self.requested.append(file_id)
        return self.resources[file_id]


ROOT = Resource("root", "Licitación", FOLDER_MIME, "1", drive_id="shared")


def test_nested_descendant_belongs_following_parent_chain_only():
    folder = Resource("folder", "Originales", FOLDER_MIME, "1", drive_id="shared", parents=("root",))
    item = Resource("item", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("folder",))
    drive = Drive(ROOT, folder)
    assert belongs_to_root(drive, ROOT, item)
    assert drive.requested == ["folder"]


def test_other_drive_trashed_or_foreign_items_do_not_belong():
    other_drive = Resource("x", "a.pdf", "application/pdf", "1", drive_id="other", parents=("root",))
    trashed = Resource("y", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("root",), trashed=True)
    foreign = Resource("z", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("unknown",))
    drive = Drive(ROOT)
    assert not belongs_to_root(drive, ROOT, other_drive)
    assert not belongs_to_root(drive, ROOT, trashed)
    assert not belongs_to_root(drive, ROOT, foreign)


def test_in_litman_is_true_for_litman_itself_and_anything_below_it():
    litman = Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",))
    inner = Resource("inner", "Borradores", FOLDER_MIME, "1", drive_id="shared", parents=("litman",))
    drive = Drive(ROOT, litman, inner)
    nested = Resource("item", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("inner",))
    assert in_litman(drive, ROOT, litman) and in_litman(drive, ROOT, inner) and in_litman(drive, ROOT, nested)


def test_in_litman_is_false_for_the_rest_of_the_tree_and_stops_at_the_root_and_unreadable_parents():
    folder = Resource("folder", "Originales", FOLDER_MIME, "1", drive_id="shared", parents=("root",))
    drive = Drive(ROOT, folder)
    item = Resource("item", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("folder",))
    assert not in_litman(drive, ROOT, item) and not in_litman(drive, ROOT, folder)
    assert drive.requested == ["folder"]
    unreadable = Resource("z", "a.pdf", "application/pdf", "1", drive_id="shared", parents=("gone",))
    drive.get = lambda file_id: (_ for _ in ()).throw(HarnessError("not_found", "x"))
    assert not in_litman(drive, ROOT, unreadable)
