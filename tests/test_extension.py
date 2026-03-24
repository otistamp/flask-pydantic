from typing import Annotated, Optional

import pytest
from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel

from flask_pydantic import FlaskPydantic
from flask_pydantic.markers import Body, Form, Query, Status


class CreateUser(BaseModel):
    name: str
    email: str


class UserQuery(BaseModel):
    limit: int = 10


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class UserForm(BaseModel):
    name: str


class NotFoundError(BaseModel):
    detail: str


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True

    @app.route("/users", methods=["POST"])
    def create_user(body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
        return UserResponse(id=1, name=body.name, email=body.email)

    @app.route("/users", methods=["GET"])
    def list_users(query: Annotated[UserQuery, Query]) -> list[UserResponse]:
        return [UserResponse(id=1, name="Jane", email="jane@example.com")]

    @app.route("/users/<int:user_id>")
    def get_user(user_id: int) -> UserResponse:
        return UserResponse(id=user_id, name="Jane", email="jane@example.com")

    @app.route("/health")
    def health() -> dict:
        return {"status": "ok"}

    FlaskPydantic(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestFunctionViews:
    def test_post_valid_body(self, client):
        resp = client.post("/users", json={"name": "Jane", "email": "jane@example.com"})
        assert resp.status_code == 201
        assert resp.json["name"] == "Jane"

    def test_post_invalid_body(self, client):
        resp = client.post("/users", json={"name": "Jane"})
        assert resp.status_code == 422
        assert "validation_error" in resp.json

    def test_get_with_query(self, client):
        resp = client.get("/users?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json, list)

    def test_path_param(self, client):
        resp = client.get("/users/42")
        assert resp.status_code == 200
        assert resp.json["id"] == 42

    def test_dict_passthrough(self, client):
        resp = client.get("/health")
        assert resp.json == {"status": "ok"}

    def test_validation_error_status_configurable(self):
        app = Flask("test")
        app.config["TESTING"] = True
        app.config["FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE"] = 400

        @app.route("/users", methods=["POST"])
        def create(body: Annotated[CreateUser, Body]) -> UserResponse:
            return UserResponse(id=1, name=body.name, email=body.email)

        FlaskPydantic(app)
        client = app.test_client()
        resp = client.post("/users", json={})
        assert resp.status_code == 400


@pytest.fixture
def method_view_app():
    app = Flask("test")
    app.config["TESTING"] = True

    class UserDetailView(MethodView):
        errors = {404: NotFoundError}

        def get(self, user_id: int) -> UserResponse:
            return UserResponse(id=user_id, name="Jane", email="jane@example.com")

        def delete(self, user_id: int) -> Annotated[None, Status(204)]:
            return None

    app.add_url_rule(
        "/users/<int:user_id>",
        view_func=UserDetailView.as_view("user_detail"),
    )
    FlaskPydantic(app)
    return app


@pytest.fixture
def method_view_client(method_view_app):
    return method_view_app.test_client()


class TestMethodView:
    def test_get(self, method_view_client):
        resp = method_view_client.get("/users/1")
        assert resp.status_code == 200
        assert resp.json["id"] == 1

    def test_delete(self, method_view_client):
        resp = method_view_client.delete("/users/1")
        assert resp.status_code == 204
        assert resp.data == b""


@pytest.fixture
def form_app():
    app = Flask("test")
    app.config["TESTING"] = True

    @app.route("/submit", methods=["POST"])
    def submit(form: Annotated[UserForm, Form]) -> UserResponse:
        return UserResponse(id=1, name=form.name, email="form@example.com")

    FlaskPydantic(app)
    return app


@pytest.fixture
def form_client(form_app):
    return form_app.test_client()


class TestFormValidation:
    def test_valid_form(self, form_client):
        resp = form_client.post(
            "/submit", data={"name": "Jane"},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 200
        assert resp.json["name"] == "Jane"

    def test_invalid_form(self, form_client):
        resp = form_client.post(
            "/submit", data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 422
        assert "validation_error" in resp.json
