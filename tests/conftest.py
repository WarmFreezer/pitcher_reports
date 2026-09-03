import itertools
import shutil
from types import SimpleNamespace

import pytest
import stripe
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.db import models
from app.db.models import db
from app.services.auth import Auth
from app.services import branding_loader, custom_report_loader, report_lab_generator

DEFAULT_PASSWORD = 'TestPass123!'

_counter = itertools.count(1)


def _uid():
    return next(_counter)


@pytest.fixture
def app(monkeypatch, tmp_path):
    # BrandingLoader/PDF_Generator resolve their school storage path relative to their own
    # module file, ignoring app.config['STORAGE'] — redirect both so tests never read/write
    # the real app/storage/schools directory in the repo.
    schools_dir = tmp_path / 'branding_schools'
    schools_dir.mkdir()
    real_default = branding_loader.BrandingLoader.SCHOOLS + '/default.json'
    shutil.copy(real_default, schools_dir / 'default.json')
    monkeypatch.setattr(branding_loader.BrandingLoader, 'SCHOOLS', str(schools_dir))
    monkeypatch.setattr(report_lab_generator, 'STORAGE_SCHOOLS', str(schools_dir))
    monkeypatch.setattr(custom_report_loader, 'STORAGE_SCHOOLS', str(schools_dir))

    flask_app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SQLALCHEMY_ENGINE_OPTIONS': {'poolclass': StaticPool},
        'SECRET_KEY': 'test-secret',
        'STORAGE': str(tmp_path / 'storage'),
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_school(app):
    def _make(**overrides):
        n = _uid()
        defaults = {
            'name': f'Test School {n}',
            'slug': f'test-school-{n}',
            'admin_email': f'admin{n}@testschool{n}.edu',
            'trackman_id': f'TST{n}',
            'stripe_subscription_status': 'active',
        }
        defaults.update(overrides)
        school = models.School(**defaults)
        db.session.add(school)
        db.session.commit()
        return school
    return _make


@pytest.fixture
def make_user(app):
    def _make(school, password=DEFAULT_PASSWORD, **overrides):
        n = _uid()
        email = overrides.pop('email', f'user{n}@{school.admin_email.split("@")[-1]}')
        first_name = overrides.pop('first_name', 'Test')
        last_name = overrides.pop('last_name', f'User{n}')
        role = overrides.pop('role', 'member')
        return Auth.create_user(email, password, first_name, last_name, school.id, role=role)
    return _make


@pytest.fixture
def make_pitcher(app):
    def _make(school, **overrides):
        n = _uid()
        defaults = {
            'school_id': school.id,
            'name': f'Pitcher {n}',
            'trackman_id': str(1000 + n),
        }
        defaults.update(overrides)
        pitcher = models.Pitcher(**defaults)
        db.session.add(pitcher)
        db.session.commit()
        return pitcher
    return _make


@pytest.fixture
def make_outing(app):
    def _make(pitcher, **overrides):
        defaults = {
            'pitcher_id': pitcher.id,
            'date': '2026-01-15',
            'pitch_count': 50,
            'lo_inning_count': 5,
            'lo_reach': 2,
            'lo_bb_count': 1,
            'two_out_ab_count': 3,
            'two_out_reach': 1,
            'two_out_bb_count': 1,
        }
        defaults.update(overrides)
        outing = models.Outing(**defaults)
        db.session.add(outing)
        db.session.commit()
        return outing
    return _make


@pytest.fixture
def make_pitch_type(app):
    def _make(**overrides):
        n = _uid()
        defaults = {'name': f'PitchType{n}', 'abbreviation': f'P{n}'}
        defaults.update(overrides)
        pitch_type = models.Pitch_Types(**defaults)
        db.session.add(pitch_type)
        db.session.commit()
        return pitch_type
    return _make


@pytest.fixture
def make_outing_pitch_stat(app):
    def _make(pitcher, outing, pitch_type, **overrides):
        defaults = {
            'pitcher_id': pitcher.id,
            'outing_id': outing.id,
            'pitch_type_id': pitch_type.id,
            'count': 20,
            'strike_count': 14,
            'sw_miss_count': 3,
            'low_quartile_speed': 88.0,
            'median_speed': 90.0,
            'high_quartile_speed': 92.0,
        }
        defaults.update(overrides)
        stat = models.Outing_Pitch_Stat(**defaults)
        db.session.add(stat)
        db.session.commit()
        return stat
    return _make


@pytest.fixture
def login_as():
    def _login(client, user, password=DEFAULT_PASSWORD):
        return client.post('/login', data={'email': user.email, 'password': password}, follow_redirects=True)
    return _login


@pytest.fixture
def mock_stripe(monkeypatch):
    checkout_session = SimpleNamespace(
        client_secret='cs_test_secret', id='cs_test_123', customer='cus_test_123',
        metadata={}, mode='subscription', subscription='sub_test_123', payment_status='paid',
    )
    subscription = SimpleNamespace(id='sub_test_123', status='active', cancel_at_period_end=False)
    invoice_list = SimpleNamespace(data=[])
    webhook_event = {'type': 'customer.subscription.updated', 'data': {'object': {'id': subscription.id, 'status': 'active'}}}

    monkeypatch.setattr(stripe.checkout.Session, 'create', lambda **kw: checkout_session)
    monkeypatch.setattr(stripe.checkout.Session, 'retrieve', lambda *a, **kw: checkout_session)
    monkeypatch.setattr(stripe.Subscription, 'retrieve', lambda *a, **kw: subscription)
    monkeypatch.setattr(stripe.Subscription, 'modify', lambda *a, **kw: subscription)
    monkeypatch.setattr(stripe.Invoice, 'list', lambda **kw: invoice_list)
    monkeypatch.setattr(stripe.Webhook, 'construct_event', lambda payload, sig, whsec: webhook_event)

    return SimpleNamespace(
        checkout_session=checkout_session,
        subscription=subscription,
        invoice_list=invoice_list,
        webhook_event=webhook_event,
    )
