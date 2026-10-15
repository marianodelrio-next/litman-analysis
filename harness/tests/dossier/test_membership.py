from __future__ import annotations

from litman_harness.dossier.membership import belongs_to_root
from litman_harness.dossier.models import FOLDER_MIME, Resource


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
