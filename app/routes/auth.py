import os
import stripe
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from flask.typing import ResponseReturnValue
from flask_login import login_user, logout_user, login_required, current_user

from app.db.models import db, User, School, TierThreeRequest
from app.services.auth import Auth, bcrypt
from app.services.notifications import notify_tier3_interest, send_password_reset_email, send_verification_email

auth_bp = Blueprint('auth', __name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Tier 3 is master-provisioned only (granted once a custom report is built for a
# school), never self-serve -- so it's read here for completeness but never looked
# up from a signup form value.
TIER_PRICE_IDS = {
    1: os.environ.get('STRIPE_TIER_1_PRICE_ID', ''),
    2: os.environ.get('STRIPE_TIER_2_PRICE_ID', ''),
    3: os.environ.get('STRIPE_TIER_3_PRICE_ID', ''),
}


@auth_bp.route('/register', methods=['GET', 'POST'])
def register() -> ResponseReturnValue:
    """New-user signup: pick a school, confirm the email matches its domain, create the account."""
    schools = School.query.order_by(School.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '')
        first_name, last_name = name.split(' ', 1) if ' ' in name else (name, '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password')
        school_name = request.form.get('school')

        # Validate passwords match and email is not already registered
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'warning')
            return redirect(url_for('auth.login'))

        # Validate school exists and email domain matches
        school = School.query.filter_by(name=school_name).first()
        if not school:
            flash('Organization not found. Please enter a valid organization.', 'danger')
            return redirect(url_for('auth.register'))

        school_domain = school.admin_email.split('@')[-1]
        if not email.endswith(f"@{school_domain}"):
            flash('Email does not match organization domain. Please use a valid organization email.', 'danger')
            return redirect(url_for('auth.register'))

        # Grant admin role if email matches the school's designated admin address
        role = 'admin' if email == school.admin_email else 'member'

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            school_id=school.id,
            role=role,
            newsletter_opt_in=bool(request.form.get('newsletter_opt_in'))
        )
        db.session.add(new_user)
        session.pop('newsletter_opt_in', None)
        db.session.commit()

        send_verification_email(new_user)
        flash('Account created! Check your email for a verification link, then log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('create_account.html', schools=schools,
                           newsletter_checked=session.get('newsletter_opt_in', False))


@auth_bp.route('/schools', methods=['GET'])
def schools() -> ResponseReturnValue:
    """Plan-select page: side-by-side tier comparison, the entry point before org signup."""
    return render_template('schools_plans.html')


@auth_bp.route('/schools/org', methods=['GET', 'POST'])
def schools_org() -> ResponseReturnValue:
    """New-school signup: collect school details, stash them in session, and start Stripe checkout.

    Tier is decided on the plan-select page (auth.schools) and carried here via ?tier= --
    only Tier 1/2 land here, since Tier 3 is never self-serve (see auth.tier3_interest)."""
    if request.method == 'POST':
        tier = request.form.get('tier', '')
        if tier not in ('1', '2'):
            flash('Please select a plan.', 'danger')
            return redirect(url_for('auth.schools'))

        school_name = request.form.get('name', '')
        school_slug = request.form.get('slug', '')
        admin_email = request.form.get('admin_email', '')
        confirm_admin_email = request.form.get('confirm_admin_email', '')

        # Validate uniqueness and admin email confirmation before touching Stripe
        if School.query.filter_by(name=school_name).first():
            flash('Organization name already exists. Please choose a different name.', 'danger')
            return redirect(url_for('auth.schools_org', tier=tier))

        if admin_email != confirm_admin_email:
            flash('Admin email addresses do not match. Please confirm the admin email.', 'danger')
            return redirect(url_for('auth.schools_org', tier=tier))

        trackman_id = request.form.get('trackman_id', '').strip()

        # Stash school data in session so return_from_checkout can create the record
        session['pending_school'] = {
            'name': school_name,
            'slug': school_slug,
            'admin_email': admin_email,
            'trackman_id': trackman_id,
            'tier': tier
        }
        # Kept apart from pending_school: that dict is sent to Stripe as metadata. Consumed by
        # register() to pre-check the admin's own signup checkbox once payment completes.
        session['newsletter_opt_in'] = bool(request.form.get('newsletter_opt_in'))

        try:
            checkout_session = stripe.checkout.Session.create(
                line_items=[{'price': TIER_PRICE_IDS[int(tier)], 'quantity': 1}],
                mode='subscription',
                ui_mode='embedded',
                return_url='http://localhost:5000/return?session_id={CHECKOUT_SESSION_ID}',
                metadata=session['pending_school'],
                customer_email=session['pending_school']['admin_email']
            )
            return redirect(url_for('payment.embedded_checkout', client_secret=checkout_session.client_secret))
        except Exception as e:
            print(str(e))
            flash('Could not start checkout. Please try again.', 'danger')
            return redirect(url_for('auth.schools_org', tier=tier))

    tier = request.args.get('tier', '')
    if tier not in ('1', '2'):
        return redirect(url_for('auth.schools'))

    return render_template('schools.html', tier=tier)


@auth_bp.route('/schools/tier3-interest', methods=['POST'])
def tier3_interest() -> ResponseReturnValue:
    """No-payment Tier 3 interest capture from the plan-select page. Hard-routes into the
    Tier 2 signup form afterward, pre-filled, rather than leaving the visitor with nothing
    to do next -- joining the queue never requires payment for either tier."""
    org_name = request.form.get('org_name', '').strip()
    contact_email = request.form.get('contact_email', '').strip()
    if not org_name or not contact_email:
        flash('Please enter your organization name and email.', 'danger')
        return redirect(url_for('auth.schools'))

    req = TierThreeRequest(org_name=org_name, contact_email=contact_email)
    db.session.add(req)
    db.session.commit()
    notify_tier3_interest(req)

    flash("You're on the list -- we'll be in touch. Want to get started with Tier 2 in the meantime?", 'success')
    return redirect(url_for('auth.schools_org', tier='2', name=org_name, admin_email=contact_email))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login() -> ResponseReturnValue:
    """Log in with email/password, honoring a ?next= redirect set by @login_required."""
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        user = Auth.get_user_by_email(email)

        if user and Auth.verify_password(user, password):
            if not user.is_active:
                flash('This account has been deactivated. Contact your school admin.', 'danger')
            elif not user.email_verified:
                # Re-send on each correct-password attempt -- doubles as the "resend" flow
                send_verification_email(user)
                flash('Please verify your email before logging in. We just sent you a new link.', 'warning')
            else:
                login_user(user, remember=request.form.get('remember'))
                # Honour the ?next= redirect param set by @login_required
                next_page = request.args.get('next')
                return redirect(next_page or url_for('pages.dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password() -> ResponseReturnValue:
    """Step 1: email a 6-digit reset code. Replies identically whether or not the account exists."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = Auth.get_user_by_email(email)
        if user and user.is_active:
            code = Auth.start_password_reset(user)
            if code:
                send_password_reset_email(user, code)
        session['reset_email'] = email
        flash('If that email has an account, we sent it a reset code.', 'info')
        return redirect(url_for('auth.reset_password_confirm'))
    return render_template('reset_password.html', step='request')


@auth_bp.route('/reset-password/confirm', methods=['GET', 'POST'])
def reset_password_confirm() -> ResponseReturnValue:
    """Step 2: exchange the emailed code for a new password."""
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('auth.reset_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 8:
            flash('New password must be at least 8 characters.', 'danger')
        elif password != request.form.get('confirm_password'):
            flash('Passwords do not match.', 'danger')
        elif Auth.finish_password_reset(email, request.form.get('code', ''), password):
            session.pop('reset_email', None)
            flash('Password updated. Please log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('That code is invalid or has expired.', 'danger')
        return redirect(url_for('auth.reset_password_confirm'))
    return render_template('reset_password.html', step='confirm')


@auth_bp.route('/verify/<token>')
def verify_email(token: str) -> ResponseReturnValue:
    """Landing page for the emailed verification link."""
    if Auth.confirm_email(token):
        flash('Email verified. You can now log in.', 'success')
    else:
        flash('That verification link is invalid or has expired. Log in to get a new one.', 'danger')
    return redirect(url_for('auth.login'))


@auth_bp.route('/unsubscribe/<token>', methods=['GET', 'POST'])
def unsubscribe(token: str) -> ResponseReturnValue:
    """One-click newsletter unsubscribe from the link in every newsletter email. POST is the
    mail-client one-click (RFC 8058) form and needs a bare 200, not a redirect."""
    if request.method == 'POST':
        return ('', 200) if Auth.unsubscribe(token) else ('', 400)
    if Auth.unsubscribe(token):
        flash('You have been unsubscribed from the newsletter.', 'success')
    else:
        flash('That unsubscribe link is invalid. You can change this in your account settings.', 'danger')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout() -> ResponseReturnValue:
    """Log out the current user."""
    logout_user()
    session.pop('master_school_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('pages.index'))
