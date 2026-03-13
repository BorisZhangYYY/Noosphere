from __future__ import annotations

from flask_restful import Api

from app.resources.auth_resources import (
    EmailVerifyResource,
    LoginResource,
    LogoutResource,
    RegisterResource,
    ResetPasswordResource,
)


def register_api_resources(api: Api) -> None:
    """Register API resources on the Flask-RESTful Api.

    Args:
        api: Flask-RESTful Api instance.
    """
    api.add_resource(RegisterResource,     "/api/auth/register")
    api.add_resource(LoginResource,        "/api/auth/login")
    api.add_resource(LogoutResource,       "/api/auth/logout")
    api.add_resource(EmailVerifyResource,  "/api/auth/email_verifying")
    api.add_resource(ResetPasswordResource, "/api/auth/reset_success")
