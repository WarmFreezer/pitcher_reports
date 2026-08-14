from flask_bcrypt import Bcrypt

from app.db import models

db = models.db
User = models.User

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
    ) -> models.User:
        """Hash password and persist a new User for the given school."""
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            school_id=school_id,
            role=role
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
    def confirm_email(email: str) -> bool:
        """Placeholder — not yet implemented; would send a confirmation token via email."""
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
        db.session.commit()
