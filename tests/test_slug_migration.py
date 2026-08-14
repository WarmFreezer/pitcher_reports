"""
Pins target behavior for the slug -> school_id migration described in
docs/test-plan-slug-migration.md (categories C and E). Most tests here are
expected to fail against current `main` -- they define the contract Phase 1c
(the actual migration implementation) must satisfy, not a regression already
in place. See the doc for full rationale and sequencing.
"""
from app.db import models


def test_duplicate_slug_schools_can_coexist(make_school):
    """
    Category E. Pins the target schema: schools.slug must no longer be unique.
    Fails against current code with sqlalchemy.exc.IntegrityError, since
    app/db/models.py:School.slug is still `unique=True` -- expected until the
    migration removes it.

    This exercises the SQLAlchemy model definition directly (via db.create_all(),
    same as the rest of this suite) -- it does not execute the Alembic migration.
    Verify that separately against a scratch Postgres/SQLite DB with
    `flask db upgrade`, mirroring how migrations/versions/95218ed0478e was
    validated (this suite doesn't exercise Alembic migrations directly for any
    existing revision either).
    """
    school_a = make_school(name='School A', slug='dup-slug')
    school_b = make_school(name='School B', slug='dup-slug')

    assert school_a.id != school_b.id
    assert school_a.slug == school_b.slug == 'dup-slug'


def test_resubscribe_webhook_resolves_school_by_id(client, make_school, mock_stripe):
    """
    Category C. Target: GET /return resolves the resubscribing school via
    Stripe metadata['school_id'], not metadata['school_slug'] -- required so
    two schools sharing a slug still resubscribe the correct one. Fails
    against current code, which reads metadata['school_slug']
    (app/routes/payments.py:43-45) and would fall through to the "new school"
    branch here (no 'name'/'slug' keys present), raising a KeyError.
    """
    school = make_school(name='Resubscribing School', stripe_subscription_status='inactive')
    mock_stripe.checkout_session.metadata = {'school_id': str(school.id)}

    resp = client.get('/return?session_id=cs_test_123', follow_redirects=False)

    assert resp.status_code == 302
    assert school.stripe_subscription_status == 'active'
    assert school.stripe_customer_id == mock_stripe.checkout_session.customer
    assert school.stripe_subscription_id == mock_stripe.checkout_session.subscription


def test_resubscribe_webhook_updates_correct_school_when_slugs_collide(client, make_school, mock_stripe):
    """
    Category C + B combined. The concrete failure mode a slug-keyed lookup
    risks once slug uniqueness is dropped: two schools share a slug, and the
    webhook must still update only the one Stripe actually identified (by id),
    never its same-slug sibling. Fails against current code for the same
    reason as test_resubscribe_webhook_resolves_school_by_id.
    """
    target = make_school(name='Target School', slug='shared-slug', stripe_subscription_status='inactive')
    other = make_school(name='Other School', slug='shared-slug', stripe_subscription_status='inactive')
    mock_stripe.checkout_session.metadata = {'school_id': str(target.id)}

    client.get('/return?session_id=cs_test_123', follow_redirects=False)

    assert target.stripe_subscription_status == 'active'
    assert other.stripe_subscription_status == 'inactive'
    assert other.stripe_customer_id is None


def test_create_user_cli_resolves_school_by_id_not_slug(app, make_school):
    """
    Category C. The `create-user` CLI command currently resolves the target
    school via `School.query.filter_by(slug=school_slug).first()`
    (app/cli.py:151), which becomes ambiguous once slug is no longer unique.
    Target: the command resolves by school id instead. Fails against current
    code, which prompts for and matches on slug.
    """
    school = make_school(name='CLI Target School')
    runner = app.test_cli_runner()

    result = runner.invoke(args=['create-user'], input=(
        'newuser@example.com\nSecretPass1!\nNew\nUser\n'
        f'{school.id}\nmember\n'
    ))

    created = models.User.query.filter_by(email='newuser@example.com').first()
    assert created is not None, result.output
    assert created.school_id == school.id
