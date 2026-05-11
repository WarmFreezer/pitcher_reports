import os
import stripe
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for

from app.db.models import db, School

payment_bp = Blueprint('payment', __name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')


@payment_bp.route('/subscribe', methods=['POST'])
def subscribe():
    # Legacy endpoint used by the embedded checkout JS — creates a session for a new school signup
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': os.environ.get('STRIPE_PRICE_ID'), 'quantity': 1}],
            mode='subscription',
            ui_mode='embedded',
            return_url='http://localhost:5000/return?session_id={CHECKOUT_SESSION_ID}',
            metadata=session['pending_school'],
            customer_email=session['pending_school']['admin_email']
        )
        return jsonify({'clientSecret': checkout_session.client_secret, 'id': checkout_session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403


@payment_bp.route('/return', methods=['GET'])
def return_from_checkout():
    session_id = request.args.get('session_id')
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)

        if checkout_session.mode == 'subscription':
            subscription_id = checkout_session.subscription
            if subscription_id:
                subscription = stripe.Subscription.retrieve(subscription_id)

                if subscription.status in ('active', 'trialing'):
                    metadata = checkout_session.metadata

                    if 'school_slug' in metadata and 'name' not in metadata:
                        # Resubscribe flow — update the existing school record
                        school = School.query.filter_by(slug=metadata['school_slug']).first()
                        if school:
                            school.stripe_customer_id = checkout_session.customer
                            school.stripe_subscription_id = subscription_id
                            school.stripe_subscription_status = subscription.status
                            db.session.commit()
                        flash('Subscription reactivated successfully!', 'success')
                        return redirect(url_for('subscription.subscription_page'))
                    else:
                        # New school signup flow — create the school record now that payment succeeded
                        db.session.add(School(
                            name=metadata['name'],
                            slug=metadata['slug'],
                            admin_email=metadata['admin_email'],
                            trackman_id=metadata.get('trackman_id') or None,
                            stripe_customer_id=checkout_session.customer,
                            stripe_subscription_id=subscription_id,
                            stripe_subscription_status=subscription.status
                        ))
                        db.session.commit()
                        session.pop('pending_school', None)
                        flash('Subscription successful! Please create your user account.', 'success')
                        return redirect(url_for('auth.register'))
                else:
                    return render_template('subscription_pending.html', subscription=subscription)

        elif checkout_session.payment_status == 'paid':
            return render_template('success.html')
        else:
            return render_template('pending.html')

    except Exception as e:
        return str(e), 403


@payment_bp.route('/checkout', methods=['GET'])
def embedded_checkout():
    client_secret = request.args.get('client_secret', '')
    if not client_secret:
        return 'Missing client_secret', 400
    return render_template(
        'embedded_checkout.html',
        client_secret=client_secret,
        stripe_publishable_key=os.environ.get('STRIPE_PUBLISHABLE_KEY')
    )


@payment_bp.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    # Verify the event came from Stripe before processing it
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, os.environ.get('STRIPE_WHSEC'))
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return str(e), 400

    data = event['data']['object']

    # Keep the school's subscription status in sync with Stripe events
    if event['type'] in ('customer.subscription.updated', 'customer.subscription.deleted'):
        school = School.query.filter_by(stripe_subscription_id=data['id']).first()
        if school:
            school.stripe_subscription_status = data['status']
            db.session.commit()

    elif event['type'] == 'invoice.payment_failed':
        school = School.query.filter_by(stripe_customer_id=data.get('customer')).first()
        if school:
            school.stripe_subscription_status = 'past_due'
            db.session.commit()

    elif event['type'] == 'invoice.payment_succeeded':
        subscription_id = data.get('subscription')
        if subscription_id:
            school = School.query.filter_by(stripe_subscription_id=subscription_id).first()
            if school:
                school.stripe_subscription_status = 'active'
                db.session.commit()

    return '', 200
