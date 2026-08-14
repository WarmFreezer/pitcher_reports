"""
One-time helper for moving a school's on-disk storage directory from the old
slug-keyed layout (storage/schools/{slug}/...) to the id-keyed layout
(storage/schools/{id}/...). See docs/test-plan-slug-migration.md, category D.
"""
import os
import shutil


def migrate_school_storage(storage_root: str, school_id: int, slug: str) -> bool:
    """
    Move storage_root/schools/{slug} to storage_root/schools/{school_id}.

    Returns True if a move was performed, False if there was nothing to do
    (no slug-keyed directory) or nothing safe to do (an id-keyed directory
    already exists — never overwritten). Safe to call repeatedly.
    """
    schools_dir = os.path.join(storage_root, 'schools')
    old_dir = os.path.join(schools_dir, slug)
    new_dir = os.path.join(schools_dir, str(school_id))

    if not os.path.isdir(old_dir):
        return False
    if os.path.exists(new_dir):
        return False

    shutil.move(old_dir, new_dir)
    return True
