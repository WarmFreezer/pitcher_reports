from flask import current_app

from app.db.models import TierThreeRequest


def notify_tier3_interest(request: TierThreeRequest) -> None:
    """Stub -- will send mail via the email service once it exists. Logs for now."""
    current_app.logger.info(f"Tier 3 interest: {request.org_name} <{request.contact_email}>")
