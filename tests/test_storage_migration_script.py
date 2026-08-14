"""
Pins the interface and behavior of the one-time storage-migration helper
described in docs/test-plan-slug-migration.md (category D). The target module
(app/services/storage_migration.py) doesn't exist yet on current `main` -- these
tests fail with ModuleNotFoundError until Phase 1c creates it, which is
expected; the tests define the contract that module must satisfy.
"""
import os

import pytest

storage_migration = pytest.importorskip(
    'app.services.storage_migration',
    reason='app/services/storage_migration.py has not been created yet (Phase 1c)',
)
migrate_school_storage = storage_migration.migrate_school_storage


def _make_slug_dir(storage_root, slug, filename='logo.png', content=b'fake-logo'):
    school_dir = os.path.join(storage_root, 'schools', slug, 'assets')
    os.makedirs(school_dir, exist_ok=True)
    path = os.path.join(school_dir, filename)
    with open(path, 'wb') as f:
        f.write(content)
    return path


def test_migrates_slug_keyed_directory_to_id_keyed(tmp_path):
    storage_root = str(tmp_path)
    _make_slug_dir(storage_root, 'old-slug')

    migrated = migrate_school_storage(storage_root, school_id=42, slug='old-slug')

    assert migrated is True
    old_dir = os.path.join(storage_root, 'schools', 'old-slug')
    new_dir = os.path.join(storage_root, 'schools', '42')
    assert not os.path.exists(old_dir)
    assert os.path.exists(os.path.join(new_dir, 'assets', 'logo.png'))


def test_idempotent_on_second_run(tmp_path):
    storage_root = str(tmp_path)
    _make_slug_dir(storage_root, 'old-slug')

    first = migrate_school_storage(storage_root, school_id=42, slug='old-slug')
    second = migrate_school_storage(storage_root, school_id=42, slug='old-slug')

    assert first is True
    assert second is False  # nothing left to migrate, must not error


def test_no_op_when_slug_directory_absent(tmp_path):
    storage_root = str(tmp_path)
    # No 'never-existed' directory is ever created.

    migrated = migrate_school_storage(storage_root, school_id=99, slug='never-existed')

    assert migrated is False


def test_does_not_clobber_existing_id_keyed_directory(tmp_path):
    storage_root = str(tmp_path)
    slug_logo = _make_slug_dir(storage_root, 'old-slug', content=b'slug-version')
    id_dir = os.path.join(storage_root, 'schools', '42', 'assets')
    os.makedirs(id_dir, exist_ok=True)
    id_logo = os.path.join(id_dir, 'logo.png')
    with open(id_logo, 'wb') as f:
        f.write(b'id-version-already-here')

    migrated = migrate_school_storage(storage_root, school_id=42, slug='old-slug')

    assert migrated is False
    with open(id_logo, 'rb') as f:
        assert f.read() == b'id-version-already-here'
    assert os.path.exists(slug_logo)
