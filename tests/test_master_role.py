"""
Covers the master role: cross-school access to /subscription via an "acting as"
session context, and the custom-report upload endpoint. See
app/routes/master.py and app/routes/utils.py's get_active_school[_id]().
"""
import io
import json
from pathlib import Path

from app.services.branding_loader import BrandingLoader
from app.services.custom_report_loader import custom_report_path


def _read_default_colors():
    return json.loads((Path(BrandingLoader.SCHOOLS) / 'default.json').read_text())['colors']


def test_non_master_cannot_list_schools(client, login_as, make_school, make_user):
    school = make_school()
    user = make_user(school, role='member')
    login_as(client, user)

    resp = client.get('/master/schools', follow_redirects=True)

    assert b'Master Panel' not in resp.data


def test_non_master_cannot_act_as_school(client, login_as, make_school, make_user):
    school_a = make_school()
    school_b = make_school()
    user = make_user(school_a, role='member')
    login_as(client, user)

    client.post(f'/master/schools/{school_b.id}/act', follow_redirects=True)

    with client.session_transaction() as sess:
        assert 'master_school_id' not in sess


def test_non_master_cannot_upload_custom_report(client, login_as, make_school, make_user):
    school = make_school()
    user = make_user(school, role='member')
    login_as(client, user)

    resp = client.post(
        f'/master/schools/{school.id}/custom-report',
        data={'report_type': 'pitcher', 'file': (io.BytesIO(b'x = 1\n'), 'custom_pitcher_report.py')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert not custom_report_path(school.id, 'custom_pitcher_report.py').exists()


def test_master_can_list_schools(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school(name='Target School')
    master = make_user(home_school, role='master')
    login_as(client, master)

    resp = client.get('/master/schools')

    assert resp.status_code == 200
    assert b'Target School' in resp.data


def test_master_acting_as_school_sees_its_subscription_page(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school(name='Target School')
    master = make_user(home_school, role='master')
    login_as(client, master)

    act_resp = client.post(f'/master/schools/{target_school.id}/act', follow_redirects=True)
    assert act_resp.status_code == 200
    assert target_school.name.encode() in act_resp.data
    assert target_school.admin_email.encode() in act_resp.data

    with client.session_transaction() as sess:
        assert sess['master_school_id'] == target_school.id


def test_master_exit_clears_session_and_blocks_subscription_access(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school(name='Target School')
    master = make_user(home_school, role='master')
    login_as(client, master)
    client.post(f'/master/schools/{target_school.id}/act')

    exit_resp = client.post('/master/exit', follow_redirects=True)

    with client.session_transaction() as sess:
        assert 'master_school_id' not in sess
    # No longer acting as anyone -- master's own school likely isn't theirs to
    # manage either (their email doesn't match their own school's admin_email)
    sub_resp = client.get('/subscription', follow_redirects=True)
    assert b'permission' in sub_resp.data.lower()


def test_logout_clears_master_session(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school(name='Target School')
    master = make_user(home_school, role='master')
    login_as(client, master)
    client.post(f'/master/schools/{target_school.id}/act')

    client.get('/logout')

    with client.session_transaction() as sess:
        assert 'master_school_id' not in sess


def test_custom_report_upload_saves_to_correct_path(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)

    resp = client.post(
        f'/master/schools/{target_school.id}/custom-report',
        data={'report_type': 'pitcher', 'file': (io.BytesIO(b'def hook():\n    return 1\n'), 'custom_pitcher_report.py')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert resp.status_code == 200
    saved_path = custom_report_path(target_school.id, 'custom_pitcher_report.py')
    assert saved_path.exists()
    assert 'def hook' in saved_path.read_text()


def test_custom_report_upload_ignores_uploaded_filename(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)

    client.post(
        f'/master/schools/{target_school.id}/custom-report',
        data={'report_type': 'pitcher', 'file': (io.BytesIO(b'x = 1\n'), 'evil.py')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert custom_report_path(target_school.id, 'custom_pitcher_report.py').exists()
    assert not custom_report_path(target_school.id, 'evil.py').exists()


def test_custom_report_upload_rejects_non_python_extension(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)

    client.post(
        f'/master/schools/{target_school.id}/custom-report',
        data={'report_type': 'hitter', 'file': (io.BytesIO(b'not python'), 'custom_hitter_report.txt')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert not custom_report_path(target_school.id, 'custom_hitter_report.py').exists()


def test_non_master_cannot_update_default_branding(client, login_as, make_school, make_user):
    school = make_school()
    user = make_user(school, role='member')
    login_as(client, user)
    original = _read_default_colors()

    client.post(
        '/master/default-branding',
        json={'colors': {'primary': '#111111', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444'}},
    )

    assert _read_default_colors() == original


def test_master_can_update_default_branding(client, login_as, make_school, make_user):
    home_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)

    resp = client.post(
        '/master/default-branding',
        json={'colors': {'primary': '#111111', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444'}},
    )

    assert resp.status_code == 200
    assert _read_default_colors() == {
        'primary': '#111111', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444',
    }


def test_master_update_default_branding_rejects_invalid_hex(client, login_as, make_school, make_user):
    home_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)
    original = _read_default_colors()

    resp = client.post(
        '/master/default-branding',
        json={'colors': {'primary': 'not-a-color', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444'}},
    )

    assert resp.status_code == 400
    assert _read_default_colors() == original


def test_custom_report_upload_rejects_syntax_error(client, login_as, make_school, make_user):
    home_school = make_school()
    target_school = make_school()
    master = make_user(home_school, role='master')
    login_as(client, master)

    client.post(
        f'/master/schools/{target_school.id}/custom-report',
        data={'report_type': 'hitter', 'file': (io.BytesIO(b'def broken(:\n'), 'custom_hitter_report.py')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert not custom_report_path(target_school.id, 'custom_hitter_report.py').exists()
