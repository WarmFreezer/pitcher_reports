import os
import stripe
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from app.db.models import db, User, School
from app.services.auth import Auth, bcrypt

auth_bp = Blueprint('auth', __name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    schools = School.query.order_by(School.name).all()

    if request.method == 'POST':
        name = request.form.get('name')
        first_name, last_name = name.split(' ', 1) if ' ' in name else (name, '')
        email = request.form.get('email')
        password = request.form.get('password')
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
            flash('School not found. Please enter a valid school.', 'danger')
            return redirect(url_for('auth.register'))

        school_domain = school.admin_email.split('@')[-1]
        if not email.endswith(f"@{school_domain}"):
            flash('Email does not match school domain. Please use a valid school email.', 'danger')
            return redirect(url_for('auth.register'))

        # Grant admin role if email matches the school's designated admin address
        role = 'admin' if email == school.admin_email else 'member'

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            school_id=school.id,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('create_account.html', schools=schools)


@auth_bp.route('/schools', methods=['GET', 'POST'])
def schools():
    if request.method == 'POST':
        school_name = request.form.get('name')
        school_slug = request.form.get('slug')
        admin_email = request.form.get('admin_email')
        confirm_admin_email = request.form.get('confirm_admin_email')

        # Validate uniqueness and admin email confirmation before touching Stripe
        if School.query.filter_by(name=school_name).first():
            flash('School name already exists. Please choose a different name.', 'danger')
            return redirect(url_for('auth.schools'))

        if admin_email != confirm_admin_email:
            flash('Admin email addresses do not match. Please confirm the admin email.', 'danger')
            return redirect(url_for('auth.schools'))

        trackman_id = request.form.get('trackman_id', '').strip()

        # Stash school data in session so return_from_checkout can create the record
        session['pending_school'] = {
            'name': school_name,
            'slug': school_slug,
            'admin_email': admin_email,
            'trackman_id': trackman_id
        }

        try:
            checkout_session = stripe.checkout.Session.create(
                line_items=[{'price': os.environ.get('STRIPE_PRICE_ID'), 'quantity': 1}],
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
            return redirect(url_for('auth.schools'))

    return render_template('schools.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = Auth.get_user_by_email(email)

        if user and Auth.verify_password(user, password):
            login_user(user, remember=request.form.get('remember'))
            # Honour the ?next= redirect param set by @login_required
            next_page = request.args.get('next')
            return redirect(next_page or url_for('pages.dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('pages.index'))
