# app/cli.py
import click
from flask.cli import with_appcontext

from app.db import models
from app.services import auth, branding_loader

Auth = auth.Auth
db = models.db
User = models.User
School = models.School
Branding_Loader = branding_loader.BrandingLoader

def register_cli_commands(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Initialize the database."""
        models.db.create_all()
        click.echo("Database initialized.")
    
    @app.cli.command("reset-db")
    @with_appcontext
    def reset_db():
        """Drop all tables and reinitialize the database. WARNING: This deletes all data!"""
        if click.confirm('This will delete all data. Are you sure?'):
            models.db.drop_all()
            models.db.create_all()
            click.echo("Database reset complete.")

    @app.cli.command("create-user-func")
    @click.argument("email")
    @click.argument("password")
    @click.option("--first-name", default="User")
    @click.option("--last-name", default="User")
    @click.option("--school-id", default=1, type=int)
    @click.option("--role", default="user")
    @with_appcontext
    def create_user_func(email, password, first_name, last_name, school_id, role):
        auth.Auth().create_user(email, password, first_name, last_name, school_id, role=role)
        click.echo(f"User {email} created.")

    @app.cli.command("create-school-func")
    @click.argument("name")
    @click.argument("slug")
    @click.argument("primary-color")
    @click.argument("secondary-color")
    @click.argument("tertiary-color")
    @click.argument("accent-color")
    @click.argument("light-color")
    @click.argument("dark-color")
    @with_appcontext
    def create_school_func(name, slug, primary_color, secondary_color, tertiary_color, accent_color, light_color, dark_color):
        """Create a new school."""        
        school = models.School(name=name, slug=slug)
        models.db.session.add(school)
        models.db.session.commit()
        
        branding_data = {
            'name': name,
            'primary_color': primary_color,
            'secondary_color': secondary_color,
            'tertiary_color': tertiary_color,
            'accent_color': accent_color,
            'light_color': light_color,
            'dark_color': dark_color,
            'logo': 'logo.png'
        }
        
        branding_loader.create_school_directory(slug, branding_data)
        click.echo(f'✓ School "{name}" created!')
        click.echo(f'  Add logo to: storage/schools/{slug}/logo.png')

    @app.cli.command("list-users")
    @with_appcontext
    def list_users():
        """List all users."""
        users = models.User.query.all()
        if not users:
            click.echo('No users found')
            return
        
        click.echo('\n=== Users ===')
        for user in users:
            click.echo(f'{user.id}. {user.email} - {user.first_name} {user.last_name} ({user.school.name}) - {user.role}')

    @app.cli.command("list-schools")
    @with_appcontext
    def list_schools():
        """List all schools."""
        schools = models.School.query.all()
        if not schools:
            click.echo('No schools found')
            return
        
        click.echo('\n=== Schools ===')
        for school in schools:
            click.echo(f'{school.id}. {school.name} ({school.slug})')
            click.echo('No users found')
        
        return
        
    @app.cli.command()
    def create_school():
        name = input("Enter school name: ")
        slug = input("Enter school slug (e.g., myschool): ")

        school = School(name=name, slug=slug)
        db.session.add(school)
        db.session.commit()

        #branding_data = {
        #    'name': name,
        #    'primary_color': input("Enter primary color (hex code, e.g., #009999): "),
        #    'secondary_color': input("Enter secondary color (hex code, e.g., #000000): "),
        #    'logo': 'logo.png'
        #}

        #Branding_Loader.create_school_dir(slug, branding_data)
        print(f"School '{name}' created with slug '{slug}' and branding initialized. Add logo to the school's assets directory.")

    @app.cli.command()
    def create_user():
        email = input("Enter user email: ")
        password = input("Enter user password: ")
        first_name = input("Enter user first name: ")
        last_name = input("Enter user last name: ")
        schools = School.query.all()
        print("\nAvailable Schools:")
        for school in schools:
            print(f"- {school.name} (slug: {school.slug})")

        school_slug = input("Enter school slug for the user: ")
        role = input("Enter user role (student/admin): ")

        school = School.query.filter_by(slug=school_slug).first()
        if not school:
            print(f"School with slug '{school_slug}' not found.")
            return

        Auth.create_user(email, password, first_name, last_name, school.id, role)
        print(f"User '{email}' created successfully with role '{role}'.")