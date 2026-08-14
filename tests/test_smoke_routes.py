"""
Breadth-first coverage: every route not already exercised in depth elsewhere gets a
status-code / no-500 / correct-redirect check here. The goal is "did I break some page",
not deep behavioral correctness — see test_auth.py, test_school_isolation.py and
test_upload_flow.py for the routes that get real assertions.
"""
import io

import pytest
from PIL import Image


# ── Public / static pages ──────────────────────────────────────────────────────

@pytest.mark.parametrize('path', ['/about', '/terms', '/privacy', '/sitemap.xml', '/robots.txt', '/favicon.ico'])
def test_public_pages_load(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_index_redirects_to_login_when_unauthenticated(client):
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_unknown_path_returns_404(client):
    resp = client.get('/this-page-does-not-exist')
    assert resp.status_code == 404


# ── Authenticated pages ─────────────────────────────────────────────────────────

@pytest.fixture
def logged_in(client, make_school, make_user, login_as):
    school = make_school()
    user = make_user(school)
    login_as(client, user)
    return school, user


@pytest.fixture
def logged_in_admin(client, make_school, make_user, login_as):
    school = make_school()
    admin = make_user(school, email=school.admin_email)
    login_as(client, admin)
    return school, admin


@pytest.mark.parametrize('path', ['/dashboard', '/upload', '/account', '/batting', '/pitching', '/api/toasts'])
def test_authenticated_pages_load(client, logged_in, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_pitching_games_is_empty_before_any_game_is_saved(client, logged_in):
    resp = client.get('/api/pitching/games')
    assert resp.status_code == 200
    assert resp.get_json() == {'games': [], 'first_date': None, 'last_date': None, 'game_count': 0}


def test_batting_hitters_is_empty_before_any_game_is_saved(client, logged_in):
    resp = client.get('/api/batting/hitters')
    assert resp.status_code == 200
    assert resp.get_json() == {'hitters': [], 'first_date': None, 'last_date': None, 'game_count': 0}


# ── Account API ──────────────────────────────────────────────────────────────────

def test_update_information_success(client, logged_in):
    resp = client.post('/api/account/information', json={'name': 'New Name', 'email': 'new@example.com'})
    assert resp.status_code == 200


def test_update_information_missing_fields(client, logged_in):
    resp = client.post('/api/account/information', json={'name': '', 'email': ''})
    assert resp.status_code == 400


def test_update_password_success(client, logged_in):
    resp = client.post('/api/account/password', json={'current_password': 'TestPass123!', 'new_password': 'NewPass456!'})
    assert resp.status_code == 200


def test_update_password_too_short(client, logged_in):
    resp = client.post('/api/account/password', json={'current_password': 'TestPass123!', 'new_password': 'short'})
    assert resp.status_code == 400


# ── Subscription page + billing (mocked Stripe) ──────────────────────────────────

def test_subscription_page_requires_admin(client, logged_in):
    resp = client.get('/subscription', follow_redirects=False)
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_subscription_page_loads_for_admin(client, logged_in_admin):
    resp = client.get('/subscription')
    assert resp.status_code == 200


def test_cancel_subscription_without_stripe_id_is_permanent(client, logged_in_admin):
    resp = client.post('/api/subscription/cancel')
    assert resp.status_code == 200
    assert resp.get_json()['permanent'] is True


def test_start_subscription_creates_checkout_session(client, logged_in_admin, mock_stripe):
    resp = client.post('/api/subscription/start')
    assert resp.status_code == 200
    assert resp.get_json()['client_secret'] == mock_stripe.checkout_session.client_secret


def test_update_subscription_settings_success(client, logged_in_admin):
    resp = client.post('/api/subscription/settings', json={'admin_email': 'new-admin@example.com'})
    assert resp.status_code == 200


def test_update_subscription_settings_rejects_invalid_email(client, logged_in_admin):
    resp = client.post('/api/subscription/settings', json={'admin_email': 'not-an-email'})
    assert resp.status_code == 400


def test_rebrand_subscription_success(client, logged_in_admin):
    colors = {'primary': '#111111', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444'}
    resp = client.post('/api/subscription/rebrand', json={'colors': colors})
    assert resp.status_code == 200


def test_rebrand_subscription_rejects_bad_hex(client, logged_in_admin):
    colors = {'primary': 'not-a-hex', 'secondary': '#222222', 'tertiary': '#333333', 'accent': '#444444'}
    resp = client.post('/api/subscription/rebrand', json={'colors': colors})
    assert resp.status_code == 400


# ── Roster ────────────────────────────────────────────────────────────────────

def test_roster_get_starts_empty(client, logged_in):
    resp = client.get('/api/subscription/roster')
    assert resp.status_code == 200
    assert resp.get_json()['roster'] == []


def test_roster_put_then_get_round_trips(client, logged_in):
    rows = [{'Trackman ID': '999', 'First Name': 'Jane', 'Last Name': 'Roe', 'Birthday': '', 'Height': '', 'Weight': ''}]
    put_resp = client.put('/api/subscription/roster', json={'rows': rows})
    assert put_resp.status_code == 200

    get_resp = client.get('/api/subscription/roster')
    roster = get_resp.get_json()['roster']
    assert any(r['Trackman ID'] == '999' for r in roster)


def test_roster_csv_upload(client, logged_in):
    csv_content = (
        "Trackman ID,First Name,Last Name,Birthday,Height,Weight\n"
        "888,John,Doe,2005-01-01,6-2,190\n"
    ).encode('utf-8')
    resp = client.post(
        '/api/subscription/roster',
        data={'file': (io.BytesIO(csv_content), 'roster.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200


# ── Logo upload ───────────────────────────────────────────────────────────────

def test_logo_upload_accepts_valid_png(client, logged_in):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), color='blue').save(buf, 'PNG')
    buf.seek(0)

    resp = client.post(
        '/api/subscription/logo',
        data={'file': (buf, 'logo.png')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200


def test_logo_upload_rejects_non_image(client, logged_in):
    resp = client.post(
        '/api/subscription/logo',
        data={'file': (io.BytesIO(b'not an image'), 'logo.png')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400


# ── Payments ──────────────────────────────────────────────────────────────────

def test_checkout_page_requires_client_secret(client):
    resp = client.get('/checkout')
    assert resp.status_code == 400


def test_checkout_page_loads_with_client_secret(client):
    resp = client.get('/checkout?client_secret=cs_test_secret')
    assert resp.status_code == 200


def test_subscribe_without_pending_school_fails_gracefully(client):
    resp = client.post('/subscribe')
    assert resp.status_code == 403


def test_return_from_checkout_resubscribe_flow(client, make_school, mock_stripe):
    school = make_school(stripe_subscription_status='canceled')
    mock_stripe.checkout_session.metadata = {'school_id': str(school.id)}

    resp = client.get('/return?session_id=cs_test_123', follow_redirects=False)

    assert resp.status_code == 302
    assert '/subscription' in resp.headers['Location']


def test_webhook_updates_subscription_status(client, make_school, mock_stripe):
    make_school(stripe_subscription_id=mock_stripe.subscription.id, stripe_subscription_status='inactive')

    resp = client.post('/webhook', data=b'{}', headers={'Stripe-Signature': 'test-sig'})

    assert resp.status_code == 200


def test_webhook_rejects_bad_signature(client, monkeypatch):
    import stripe

    def _raise(*a, **kw):
        raise ValueError('bad payload')
    monkeypatch.setattr(stripe.Webhook, 'construct_event', _raise)

    resp = client.post('/webhook', data=b'{}', headers={'Stripe-Signature': 'bad'})
    assert resp.status_code == 400
