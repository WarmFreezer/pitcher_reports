from app.db.models import db
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


# ── Email verification ──────────────────────────────────────────────────────

def test_register_admin_sends_verification_and_blocks_login(client, make_school, monkeypatch):
    sent = []
    monkeypatch.setattr('app.routes.auth.send_verification_email', lambda u: sent.append(u.email))
    school = make_school()
    client.post('/register', data=_register_payload(school, email=school.admin_email), follow_redirects=True)

    assert sent == [school.admin_email]
    assert User.query.filter_by(email=school.admin_email).first().email_verified is False

    resp = client.post('/login', data={'email': school.admin_email, 'password': 'StrongPass123!'})
    assert resp.status_code == 200  # re-rendered login, not a redirect into the app
    assert len(sent) == 2  # login attempt re-sent the link


def test_register_member_must_verify_too(client, make_school, monkeypatch):
    sent = []
    monkeypatch.setattr('app.routes.auth.send_verification_email', lambda u: sent.append(u.email))
    school = make_school()
    payload = _register_payload(school)
    client.post('/register', data=payload)

    assert sent == [payload['email']]
    resp = client.post('/login', data={'email': payload['email'], 'password': payload['password']})
    assert resp.status_code == 200  # blocked until verified


def test_verify_link_unlocks_admin_login(client, make_school):
    from app.services.auth import Auth
    school = make_school()
    admin = Auth.create_user(school.admin_email, 'StrongPass123!', 'A', 'B', school.id,
                             role='admin', email_verified=False)

    resp = client.get(f'/verify/{Auth.verification_token(admin.email)}')
    assert resp.status_code == 302
    assert db.session.get(User, admin.id).email_verified is True


def test_verify_rejects_tampered_and_expired_tokens(client, make_school, monkeypatch):
    from app.services import auth as auth_mod
    from app.services.auth import Auth
    school = make_school()
    admin = Auth.create_user(school.admin_email, 'StrongPass123!', 'A', 'B', school.id,
                             role='admin', email_verified=False)
    token = Auth.verification_token(admin.email)

    assert Auth.confirm_email(token + 'x') is False
    monkeypatch.setattr(auth_mod, 'VERIFY_MAX_AGE', -1)
    assert Auth.confirm_email(token) is False
    assert db.session.get(User, admin.id).email_verified is False


# ── Newsletter ──────────────────────────────────────────────────────────────

def test_signup_newsletter_opt_in_defaults_off_and_checkbox_sets_it(client, make_school, monkeypatch):
    monkeypatch.setattr('app.routes.auth.send_verification_email', lambda u: True)
    school = make_school()
    client.post('/register', data=_register_payload(school, email=f'a@{school.admin_email.split("@")[-1]}'))
    client.post('/register', data=_register_payload(school, email=f'b@{school.admin_email.split("@")[-1]}',
                                                    newsletter_opt_in='1'))
    assert User.query.filter_by(email=f'a@{school.admin_email.split("@")[-1]}').first().newsletter_opt_in is False
    assert User.query.filter_by(email=f'b@{school.admin_email.split("@")[-1]}').first().newsletter_opt_in is True


def test_unsubscribe_token_opts_user_out(client, make_school, make_user):
    from app.services.auth import Auth
    user = make_user(make_school())
    user.newsletter_opt_in = True
    db.session.commit()

    assert Auth.unsubscribe(Auth.unsubscribe_token(user.email) + 'x') is False
    assert client.get(f'/unsubscribe/{Auth.unsubscribe_token(user.email)}').status_code == 302
    assert db.session.get(User, user.id).newsletter_opt_in is False


def test_send_newsletter_filters_limits_and_resumes(app, make_school, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr('app.services.notifications.send_email', lambda to, *a, **k: sent.append(to) or True)
    school = make_school()
    opted = [make_user(school) for _ in range(3)]
    for u in opted:
        u.newsletter_opt_in = True
    opted[2].email_verified = False  # unverified: never mailed
    make_user(school)                # not opted in: never mailed
    db.session.commit()

    monkeypatch.setenv('NEWSLETTER_ADDRESS', '1 Test St')
    runner = app.test_cli_runner()
    path = 'newsletter.html'
    with runner.isolated_filesystem():
        open(path, 'w').write('<p>hi</p>')
        r1 = runner.invoke(args=['send-newsletter', 'c1', 'Subj', path, '--limit', '1'])
        r2 = runner.invoke(args=['send-newsletter', 'c1', 'Subj', path, '--limit', '1'])
        r3 = runner.invoke(args=['send-newsletter', 'c1', 'Subj', path, '--limit', '1'])
    assert sent == [opted[0].email, opted[1].email]
    assert '1 remaining' in r1.output and '0 remaining' in r2.output and 'Sent 0/0' in r3.output


# ── Password reset ──────────────────────────────────────────────────────────

def _request_code(client, user, monkeypatch):
    codes = []
    monkeypatch.setattr('app.routes.auth.send_password_reset_email', lambda u, code: codes.append(code))
    client.post('/reset-password', data={'email': user.email})
    return codes


def test_password_reset_happy_path_and_code_is_single_use(client, make_school, make_user, monkeypatch):
    user = make_user(make_school())
    user.email_verified = False
    db.session.commit()
    codes = _request_code(client, user, monkeypatch)
    assert len(codes) == 1 and len(codes[0]) == 6

    data = {'code': codes[0], 'password': 'BrandNewPass1!', 'confirm_password': 'BrandNewPass1!'}
    assert client.post('/reset-password/confirm', data=data).headers['Location'].endswith('/login')
    db.session.refresh(user)
    assert user.email_verified is True  # code proved mailbox ownership
    assert client.post('/login', data={'email': user.email, 'password': 'BrandNewPass1!'}).status_code == 302

    from app.services.auth import Auth
    assert Auth.finish_password_reset(user.email, codes[0], 'AnotherPass123!') is False


def test_password_reset_unknown_email_looks_identical_and_sends_nothing(client, monkeypatch):
    sent = []
    monkeypatch.setattr('app.routes.auth.send_password_reset_email', lambda u, c: sent.append(1))
    resp = client.post('/reset-password', data={'email': 'nobody@nowhere.com'})
    assert resp.headers['Location'].endswith('/reset-password/confirm') and sent == []


def test_password_reset_wrong_code_burns_after_max_attempts(client, make_school, make_user, monkeypatch):
    from app.services.auth import Auth, RESET_MAX_ATTEMPTS
    user = make_user(make_school())
    codes = _request_code(client, user, monkeypatch)
    for _ in range(RESET_MAX_ATTEMPTS):
        assert Auth.finish_password_reset(user.email, '000000' if codes[0] != '000000' else '111111', 'NewPass1234!') is False
    assert Auth.finish_password_reset(user.email, codes[0], 'NewPass1234!') is False  # right code, too late


def test_password_reset_expired_code_and_resend_throttle(client, make_school, make_user, monkeypatch):
    from datetime import datetime, timedelta
    from app.services.auth import Auth
    user = make_user(make_school())
    codes = _request_code(client, user, monkeypatch)
    _request_code(client, user, monkeypatch)  # within the gap: throttled, no new code
    assert Auth.start_password_reset(user) is None

    user.reset_code_expires = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    assert Auth.finish_password_reset(user.email, codes[0], 'NewPass1234!') is False
