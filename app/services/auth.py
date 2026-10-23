import hmac
import secrets
from datetime import datetime, timedelta

from flask import current_app
from flask_bcrypt import Bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.db import models

db = models.db
User = models.User

VERIFY_MAX_AGE = 24 * 60 * 60  # seconds a verification link stays valid
RESET_TTL = 15 * 60            # seconds a password-reset code stays valid
RESET_MAX_ATTEMPTS = 5         # wrong guesses before the code is burned
RESET_RESEND_GAP = 60          # seconds before another code can be requested

# Single shared bcrypt instance — imported by routes that need to hash passwords directly
bcrypt = Bcrypt()


class Auth:
    """Password hashing and account-field updates for the User model."""

    @staticmethod
    def create_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        school_id: int,
        role: str = 'student',
        email_verified: bool = True,
    ) -> models.User:
        """Hash password and persist a new User for the given school. Defaults to verified
        because the callers (CLI, tests) are operator-provisioned; self-signup passes False."""
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            school_id=school_id,
            role=role,
            email_verified=email_verified,
        )
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def verify_password(user: models.User, password: str) -> bool:
        """Whether password matches the user's stored hash."""
        return bcrypt.check_password_hash(user.password_hash, password)

    @staticmethod
    def get_user_by_email(email: str) -> models.User | None:
        """Look up a user by email, or None if no account uses it."""
        return User.query.filter_by(email=email).first()

    @staticmethod
    def update_password(user: models.User, old_password: str, new_password: str) -> None:
        """Re-hash and persist new_password after confirming old_password is correct."""
        if not Auth.verify_password(user, old_password):
            raise ValueError("Current password is incorrect.")
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()

    @staticmethod
    def update_name(user: models.User, first_name: str, last_name: str) -> None:
        """Update and persist the user's display name."""
        user.first_name = first_name
        user.last_name = last_name
        db.session.commit()

    @staticmethod
    def _serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='email-verify')

    @staticmethod
    def verification_token(email: str) -> str:
        """Signed token carrying the address being verified."""
        return Auth._serializer().dumps(email)

    @staticmethod
    def _reset_hash(email: str, code: str) -> str:
        return hmac.new(current_app.config['SECRET_KEY'].encode(), f"{email}:{code}".encode(), 'sha256').hexdigest()

    @staticmethod
    def start_password_reset(user: models.User) -> str | None:
        """Issue a fresh 6-digit code (stored hashed) and return it, or None if one was
        issued under RESET_RESEND_GAP seconds ago (stops the form being used to spam inboxes)."""
        now = datetime.now()
        if user.reset_code_expires and user.reset_code_expires - timedelta(seconds=RESET_TTL) > now - timedelta(seconds=RESET_RESEND_GAP):
            return None
        code = f"{secrets.randbelow(10**6):06d}"
        user.reset_code_hash = Auth._reset_hash(user.email, code)
        user.reset_code_expires = now + timedelta(seconds=RESET_TTL)
        user.reset_attempts = 0
        db.session.commit()
        return code

    @staticmethod
    def finish_password_reset(email: str, code: str, new_password: str) -> bool:
        """Set a new password if code matches the live one for this email. Also marks the email
        verified -- the code proves mailbox ownership. A wrong guess counts; the code dies at RESET_MAX_ATTEMPTS."""
        user = Auth.get_user_by_email(email)
        if not user or not user.reset_code_hash:
            return False
        if user.reset_code_expires is None or user.reset_code_expires < datetime.now() or user.reset_attempts >= RESET_MAX_ATTEMPTS:
            user.reset_code_hash = None
            db.session.commit()
            return False
        if not hmac.compare_digest(user.reset_code_hash, Auth._reset_hash(user.email, code.strip())):
            user.reset_attempts += 1
            db.session.commit()
            return False
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.email_verified = True
        user.reset_code_hash = None
        db.session.commit()
        return True

    @staticmethod
    def unsubscribe_token(email: str) -> str:
        """Signed, non-expiring token for the newsletter unsubscribe link."""
        return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='newsletter-unsub').dumps(email)

    @staticmethod
    def unsubscribe(token: str) -> bool:
        """Opt the token's user out of the newsletter. False if the token is bad or the user is gone."""
        try:
            email = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='newsletter-unsub').loads(token)
        except BadSignature:
            return False
        user = Auth.get_user_by_email(email)
        if not user:
            return False
        user.newsletter_opt_in = False
        db.session.commit()
        return True

    @staticmethod
    def confirm_email(token: str) -> bool:
        """Mark the token's address verified. False if the token is bad, expired, or the
        address no longer belongs to an account (e.g. the user changed their email)."""
        try:
            email = Auth._serializer().loads(token, max_age=VERIFY_MAX_AGE)
        except BadSignature:
            return False
        user = Auth.get_user_by_email(email)
        if not user:
            return False
        user.email_verified = True
        db.session.commit()
        return True

    @staticmethod
    def update_email(user: models.User, new_email: str) -> None:
        """Update the user's email, keeping the school's admin_email in sync if they're the admin."""
        if User.query.filter_by(email=new_email).first():
            raise ValueError("Email is already in use.")

        # Keep the school's admin_email in sync if this user is the admin
        if user.school.admin_email == user.email:
            user.school.admin_email = new_email

        user.email = new_email
        user.email_verified = False
        db.session.commit()
