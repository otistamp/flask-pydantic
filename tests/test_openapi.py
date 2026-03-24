from typing import Annotated, Optional

import pytest
from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel, Field

from flask_pydantic import FlaskPydantic
from flask_pydantic.docs_decorator import docs
from flask_pydantic.markers import Body, Query, Status
from flask_pydantic.openapi import generate_openapi_spec


class CreateUser(BaseModel):
    """Create a user."""
    name: str = Field(description="Full name", examples=["Jane"])
    email: str = Field(description="Email address")


class UserResponse(BaseModel):
    """A user resource."""
    id: int
    name: str
    email: str


class NotFoundError(BaseModel):
    """Not found."""
    detail: str


class UserQuery(BaseModel):
    limit: int = Field(10, description="Max results")


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True

    @app.route("/users", methods=["POST"])
    @docs(tag="Users", summary="Create user")
    def create_user(body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
        """Creates a new user."""
        ...

    @app.route("/users", methods=["GET"])
    @docs(tag="Users")
    def list_users(query: Annotated[UserQuery, Query]) -> list[UserResponse]:
        ...

    @app.route("/users/<int:user_id>")
    @docs(errors={404: NotFoundError})
    def get_user(user_id: int) -> UserResponse:
        """Get a single user."""
        ...

    FlaskPydantic(app)
    return app


class TestOpenAPISpec:
    def test_spec_structure(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        assert spec["openapi"] == "3.1.0"
        assert "info" in spec
        assert "paths" in spec

    def test_post_endpoint(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        post_op = spec["paths"]["/users"]["post"]
        assert post_op["summary"] == "Create user"
        assert post_op["tags"] == ["Users"]
        assert "requestBody" in post_op
        assert "201" in post_op["responses"]

    def test_get_endpoint_query_params(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        get_op = spec["paths"]["/users"]["get"]
        assert any(p["name"] == "limit" for p in get_op.get("parameters", []))

    def test_path_param(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        get_op = spec["paths"]["/users/{user_id}"]["get"]
        path_params = [p for p in get_op["parameters"] if p["in"] == "path"]
        assert len(path_params) == 1
        assert path_params[0]["name"] == "user_id"

    def test_error_responses(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        get_op = spec["paths"]["/users/{user_id}"]["get"]
        assert "404" in get_op["responses"]

    def test_auto_validation_error(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        post_op = spec["paths"]["/users"]["post"]
        assert "422" in post_op["responses"]

    def test_schemas_in_components(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        schemas = spec.get("components", {}).get("schemas", {})
        assert "CreateUser" in schemas
        assert "UserResponse" in schemas

    def test_list_response_is_array(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        get_op = spec["paths"]["/users"]["get"]
        schema = get_op["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["type"] == "array"

    def test_operation_description_from_docstring(self, app):
        with app.app_context():
            spec = generate_openapi_spec(app)
        post_op = spec["paths"]["/users"]["post"]
        assert post_op["description"] == "Creates a new user."


class TestMethodViewOpenAPI:
    @pytest.fixture
    def mv_app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        class UserDetailView(MethodView):
            errors = {404: NotFoundError}

            def get(self, user_id: int) -> UserResponse:
                """Get user by ID."""
                ...

            def delete(self, user_id: int) -> Annotated[None, Status(204)]:
                """Delete a user."""
                ...

        app.add_url_rule(
            "/users/<int:user_id>",
            view_func=UserDetailView.as_view("user_detail"),
        )
        FlaskPydantic(app)
        return app

    def test_method_view_get(self, mv_app):
        with mv_app.app_context():
            spec = generate_openapi_spec(mv_app)
        get_op = spec["paths"]["/users/{user_id}"]["get"]
        assert "200" in get_op["responses"]
        assert "404" in get_op["responses"]

    def test_method_view_delete_204(self, mv_app):
        with mv_app.app_context():
            spec = generate_openapi_spec(mv_app)
        del_op = spec["paths"]["/users/{user_id}"]["delete"]
        assert "204" in del_op["responses"]
