import pytest
from flask import Flask
from flask_pydantic import api, generate_openapi_spec


class TestFlaskPathToOpenapi:
    """Test the internal path conversion helper."""

    def test_simple_path(self):
        from flask_pydantic.openapi import _flask_path_to_openapi

        assert _flask_path_to_openapi("/users") == "/users"

    def test_typed_param(self):
        from flask_pydantic.openapi import _flask_path_to_openapi

        assert _flask_path_to_openapi("/users/<int:user_id>") == "/users/{user_id}"

    def test_untyped_param(self):
        from flask_pydantic.openapi import _flask_path_to_openapi

        assert _flask_path_to_openapi("/users/<username>") == "/users/{username}"

    def test_multiple_params(self):
        from flask_pydantic.openapi import _flask_path_to_openapi

        assert (
            _flask_path_to_openapi("/users/<int:user_id>/posts/<int:post_id>")
            == "/users/{user_id}/posts/{post_id}"
        )


class TestBasicSpecStructure:
    @pytest.fixture
    def app(self):
        app = Flask("test_app")
        app.config["TESTING"] = True

        @app.route("/health")
        @api(validate=False)
        def health():
            """Health check endpoint."""
            return {"status": "ok"}

        return app

    def test_spec_has_required_keys(self, app):
        spec = generate_openapi_spec(app)
        assert spec["openapi"] == "3.1.0"
        assert "info" in spec
        assert "paths" in spec

    def test_spec_info_defaults(self, app):
        spec = generate_openapi_spec(app)
        assert spec["info"]["title"] == "test_app"
        assert spec["info"]["version"] == "1.0.0"

    def test_spec_info_custom(self, app):
        spec = generate_openapi_spec(
            app, title="My API", version="2.0.0", description="A test API"
        )
        assert spec["info"]["title"] == "My API"
        assert spec["info"]["version"] == "2.0.0"
        assert spec["info"]["description"] == "A test API"

    def test_decorated_route_included(self, app):
        spec = generate_openapi_spec(app)
        assert "/health" in spec["paths"]
        assert "get" in spec["paths"]["/health"]

    def test_undecorated_route_excluded(self, app):
        @app.route("/bare")
        def bare():
            return "hi"

        spec = generate_openapi_spec(app)
        assert "/bare" not in spec["paths"]

    def test_static_route_excluded(self, app):
        spec = generate_openapi_spec(app)
        for path in spec["paths"]:
            assert "static" not in path
