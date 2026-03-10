import os
import stripe
from flask import render_template, request, jsonify, session, flash, redirect, url_for

from app.db import models

db = models.db
User = models.User
School = models.School

class PaymentRoutes:
    def __init__(self, app, stripe_publishable_key):
        self.app = app
        self.stripe_publishable_key = stripe_publishable_key
        self._register_routes()

    def _register_routes(self):
        @self.app.route('/subscribe', methods=['POST'])
        def subscribe():
            try:
                checkout_session = stripe.checkout.Session.create(
                    line_items=[{
                        'price': os.environ.get('STRIPE_PRICE_ID'),
                        'quantity': 1,
                    }],
                    mode='subscription',
                    ui_mode='embedded',
                    return_url='http://localhost:5000/return?session_id={CHECKOUT_SESSION_ID}',
                    metadata=session['pending_school'],  # Pass pending school data to Stripe metadata
                    customer_email=session['pending_school']['admin_email']  # Pre-fill admin email in Stripe Checkout
                )
                return jsonify({
                    'clientSecret': checkout_session.client_secret,
                    'id': checkout_session.id
                })
            except Exception as e:
                return jsonify(error=str(e)), 403

        @self.app.route('/return', methods=['GET'])
        def return_from_checkout():
            session_id = request.args.get('session_id')
            try:
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                
                # For subscriptions, check the subscription status
                if checkout_session.mode == 'subscription':
                    # Get the subscription ID from the session
                    subscription_id = checkout_session.subscription
                    if subscription_id:
                        # Retrieve the subscription
                        subscription = stripe.Subscription.retrieve(subscription_id)
                        
                        if subscription.status == 'active' or subscription.status == 'trialing':
                            metadata = checkout_session.metadata
                            db.session.add(School(
                                name=metadata['name'],
                                slug=metadata['slug'],
                                admin_email=metadata['admin_email'],
                                stripe_customer_id=checkout_session.customer,
                                stripe_subscription_id=subscription_id,
                                stripe_subscription_status=subscription.status
                            ))
                            db.session.commit()

                            session.pop('pending_school', None)

                            flash('Subscription successful! Please create your user account.', 'success')
                            return redirect(url_for('register'))
                        else:
                            return render_template('subscription_pending.html', 
                                                subscription=subscription)
                
                # Fallback for non-subscription checkouts
                elif checkout_session.payment_status == "paid":
                    return render_template('success.html')
                else:
                    return render_template('pending.html')
                    
            except Exception as e:
                return str(e), 403

        @self.app.route('/checkout', methods=['GET'])
        def embedded_checkout():
            client_secret = request.args.get('client_secret', '')
            if not client_secret:
                return 'Missing client_secret', 400
            return render_template(
                'embedded_checkout.html',
                client_secret=client_secret,
                stripe_publishable_key=self.stripe_publishable_key
            )

        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            payload = request.data
            sig_header = request.headers.get('Stripe-Signature')
            webhook_secret = os.environ.get('STRIPE_WHSEC')

            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            except (ValueError, stripe.error.SignatureVerificationError) as e:
                return str(e), 400

            data = event['data']['object']

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