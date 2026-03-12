from __future__ import annotations

from flask_restful import Api

from app.resources.login_resources import UserLoginResource
from app.resources.auth_resources import (
    EmailVerifyResource,
    LoginResource,
    LogoutResource,
    ResetPasswordResource,
)


def register_api_resources(api: Api) -> None:
    """Register API resources on the Flask-RESTful Api.

    Args:
        api: Flask-RESTful Api instance.
    """
    api.add_resource(UserLoginResource,    "/api/auth/register")
    api.add_resource(LoginResource,        "/api/auth/login")
    api.add_resource(LogoutResource,       "/api/auth/logout")
    api.add_resource(EmailVerifyResource,  "/api/auth/email_verifying")
    api.add_resource(ResetPasswordResource, "/api/auth/reset_success")
