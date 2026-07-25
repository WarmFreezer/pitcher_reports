from app.db.models import User


def _register_payload(school, **overrides):
    payload = {
        'name': 'Jane Smith',
        'email': f'jane@{school.admin_email.split("@")[-1]}',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
        'school': school.name,
    }
    payload.update(overrides)
    return payload


def test_register_success_creates_member_user(client, make_school):
    school = make_school()
    resp = client.post('/register', data=_register_payload(school), follow_redirects=True)

    assert resp.status_code == 200
    user = User.query.filter_by(email=_register_payload(school)['email']).first()
    assert user is not None
    assert user.role == 'member'
    assert user.school_id == school.id


def test_register_admin_email_gets_admin_role(client, make_school):
    school = make_school()
    payload = _register_payload(school, name='Admin Person', email=school.admin_email)
    client.post('/register', data=payload, follow_redirects=True)

    user = User.query.filter_by(email=school.admin_email).first()
    assert user is not None
    assert user.role == 'admin'


def test_register_rejects_mismatched_passwords(client, make_school):
    school = make_school()
    payload = _register_payload(school, confirm_password='Different123!')
    resp = client.post('/register', data=payload, follow_redirects=True)

    assert resp.status_code == 200
    assert User.query.filter_by(email=payload['email']).first() is None


def test_register_rejects_duplicate_email(client, make_school, make_user):
    school = make_school()
    existing = make_user(school)
    payload = _register_payload(school, email=existing.email)

    resp = client.post('/register', data=payload, follow_redirects=True)

    assert resp.status_code == 200
    # Still only the one user with that email
    assert User.query.filter_by(email=existing.email).count() == 1


def test_register_rejects_email_outside_school_domain(client, make_school):
    school = make_school()
    payload = _register_payload(school, email='jane@some-other-domain.com')

    client.post('/register', data=payload, follow_redirects=True)

    assert User.query.filter_by(email='jane@some-other-domain.com').first() is None


def test_login_success_redirects_to_dashboard(client, make_school, make_user, login_as):
    school = make_school()
    user = make_user(school)

    resp = login_as(client, user)

    assert resp.status_code == 200
    assert resp.request.path == '/dashboard'


def test_login_wrong_password_shows_error(client, make_school, make_user):
    school = make_school()
    user = make_user(school)

    resp = client.post('/login', data={'email': user.email, 'password': 'wrong'}, follow_redirects=True)

    assert resp.status_code == 200
    assert b'Invalid email or password' in resp.data


def test_login_honors_next_param(client, make_school, make_user):
    school = make_school()
    user = make_user(school)

    resp = client.post(
        '/login?next=/account',
        data={'email': user.email, 'password': 'TestPass123!'},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers['Location'] == '/account'


def test_already_logged_in_user_hitting_login_redirects_to_dashboard(client, make_school, make_user, login_as):
    school = make_school()
    user = make_user(school)
    login_as(client, user)

    resp = client.get('/login', follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers['Location'] == '/dashboard'


def test_logout_requires_login(client):
    resp = client.get('/logout', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_logout_clears_session(client, make_school, make_user, login_as):
    school = make_school()
    user = make_user(school)
    login_as(client, user)

    client.get('/logout')
    resp = client.get('/dashboard', follow_redirects=False)

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
