from __future__ import annotations

from flask import Flask
from flask_restful import Api

from app.routes import register_api_resources


def create_api(app: Flask) -> Api:
    """Create a Flask-RESTful Api and register all resources.

    Args:
        app: Flask application instance.

    Returns:
        A Flask-RESTful Api instance.
    """
    api = Api(app)
    register_api_resources(api)
    return api
