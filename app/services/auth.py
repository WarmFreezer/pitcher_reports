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
    
    @staticmethod
    def update_password(user, old_password, new_password):
        if not Auth.verify_password(user, old_password):
            raise ValueError("Current password is incorrect.")
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()

    @staticmethod 
    def update_name(user, first_name, last_name):
        user.first_name = first_name
        user.last_name = last_name
        db.session.commit()

    @staticmethod 
    def confirm_email(email):
        return True #Placeholder for email confirmation logic (e.g. sending a confirmation email with a token)

    @staticmethod
    def update_email(user, new_email):
        if User.query.filter_by(email=new_email).first():
            raise ValueError("Email is already in use.")
        
        if User.school.admin_email == user.email:
            user.school.admin_email = new_email
        
        user.email = new_email
        db.session.commit()

    @staticmethod
    def update_name(user, first_name, last_name):
        user.first_name = first_name
        user.last_name = last_name
        db.session.commit()
