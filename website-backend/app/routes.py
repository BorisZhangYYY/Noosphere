from __future__ import annotations

from flask_restful import Api

from app.resources.login_resources import UserLoginResource


def register_api_resources(api: Api) -> None:
    """Register API resources on the Flask-RESTful Api.

    Args:
        api: Flask-RESTful Api instance.
    """
    api.add_resource(UserLoginResource, "/api/auth/register")
