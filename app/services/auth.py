from flask_bcrypt import Bcrypt

from app.db import models

db = models.db
User = models.User

bcrypt = Bcrypt()

class Auth:
    @staticmethod 
    def create_user(email, password, first_name, last_name, school_id, role='student'):
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
    def verify_password(user, password):
        return bcrypt.check_password_hash(user.password_hash, password)
    
    @staticmethod 
    def get_user_by_email(email):
        return User.query.filter_by(email=email).first()
