"""Tests for the @validate backwards-compatibility shim."""
from typing import List, Optional

import pytest
from flask import Flask, request
from pydantic import BaseModel

from flask_pydantic import FlaskPydantic, validate


class QueryModel(BaseModel):
    limit: int = 10
    min_views: Optional[int] = None


class BodyModel(BaseModel):
    name: str
    nickname: Optional[str] = None


class FormModel(BaseModel):
    name: str
    nickname: Optional[str] = None


class ResponseModel(BaseModel):
    id: int
    name: str
    nickname: Optional[str] = None


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True

    @app.route("/explicit", methods=["POST"])
    @validate(body=BodyModel, query=QueryModel)
    def explicit_post():
        return ResponseModel(
            id=1,
            name=request.body_params.name,
            nickname=request.body_params.nickname,
        )

    @app.route("/kwargs", methods=["POST"])
    @validate()
    def kwargs_post(body: BodyModel, query: QueryModel):
        return ResponseModel(id=2, name=body.name, nickname=body.nickname)

    @app.route("/form", methods=["POST"])
    @validate(form=FormModel)
    def form_post():
        return ResponseModel(
            id=3,
            name=request.form_params.name,
            nickname=request.form_params.nickname,
        )

    @app.route("/many", methods=["GET"])
    @validate(response_many=True)
    def get_many():
        return [
            ResponseModel(id=1, name="A"),
            ResponseModel(id=2, name="B"),
        ]

    @app.route("/status", methods=["POST"])
    @validate(body=BodyModel, on_success_status=201)
    def with_status():
        return ResponseModel(id=4, name=request.body_params.name)

    @app.route("/exclude", methods=["POST"])
    @validate(body=BodyModel, exclude_none=True)
    def with_exclude_none():
        return ResponseModel(id=5, name=request.body_params.name, nickname=None)

    FlaskPydantic(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestExplicitModels:
    def test_valid_post(self, client):
        resp = client.post("/explicit?limit=5", json={"name": "Jane"})
        assert resp.status_code == 200
        assert resp.json["name"] == "Jane"

    def test_invalid_body(self, client):
        resp = client.post("/explicit", json={})
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "body_params" in resp.json["validation_error"]

    def test_invalid_query(self, client):
        resp = client.post("/explicit?limit=abc", json={"name": "Jane"})
        assert resp.status_code == 422
        assert "query_params" in resp.json["validation_error"]


class TestKwargsStyle:
    def test_valid_post(self, client):
        resp = client.post("/kwargs?limit=5", json={"name": "Jane"})
        assert resp.status_code == 200
        assert resp.json["name"] == "Jane"

    def test_invalid_body(self, client):
        resp = client.post("/kwargs", json={})
        assert resp.status_code == 422


class TestFormValidation:
    def test_valid_form(self, client):
        resp = client.post(
            "/form", data={"name": "Jane"},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 200
        assert resp.json["name"] == "Jane"


class TestResponseMany:
    def test_many(self, client):
        resp = client.get("/many")
        assert resp.status_code == 200
        assert isinstance(resp.json, list)
        assert len(resp.json) == 2


class TestOnSuccessStatus:
    def test_custom_status(self, client):
        resp = client.post("/status", json={"name": "Jane"})
        assert resp.status_code == 201


class TestExcludeNone:
    def test_none_excluded(self, client):
        resp = client.post("/exclude", json={"name": "Jane"})
        assert resp.status_code == 200
        assert "nickname" not in resp.json
