from typing import Annotated

import pytest
from flask import Flask
from pydantic import BaseModel

from flask_pydantic import FlaskPydantic
from flask_pydantic.markers import Body


class Item(BaseModel):
    name: str


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True

    @app.route("/items", methods=["POST"])
    def create_item(body: Annotated[Item, Body]) -> Item:
        return body

    FlaskPydantic(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestOpenAPIEndpoints:
    def test_json_spec(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        data = resp.json
        assert data["openapi"] == "3.1.0"
        assert "/items" in data["paths"]

    def test_swagger_ui(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert b"swagger-ui" in resp.data

    def test_redoc(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert b"redoc" in resp.data.lower()


class TestDisabledEndpoints:
    def test_disabled_docs(self):
        app = Flask("test")
        app.config["TESTING"] = True
        app.config["FLASK_PYDANTIC_DOCS_URL"] = None

        @app.route("/items", methods=["POST"])
        def create_item(body: Annotated[Item, Body]) -> Item:
            return body

        FlaskPydantic(app)
        client = app.test_client()
        resp = client.get("/docs")
        assert resp.status_code == 404

    def test_disabled_redoc(self):
        app = Flask("test")
        app.config["TESTING"] = True
        app.config["FLASK_PYDANTIC_REDOC_URL"] = None

        @app.route("/items", methods=["POST"])
        def create_item(body: Annotated[Item, Body]) -> Item:
            return body

        FlaskPydantic(app)
        client = app.test_client()
        resp = client.get("/redoc")
        assert resp.status_code == 404


class TestCustomCDN:
    def test_custom_cdn_url(self):
        app = Flask("test")
        app.config["TESTING"] = True
        app.config["FLASK_PYDANTIC_CDN_URL"] = "https://cdn.example.com"

        @app.route("/items", methods=["POST"])
        def create_item(body: Annotated[Item, Body]) -> Item:
            return body

        FlaskPydantic(app)
        client = app.test_client()
        resp = client.get("/docs")
        assert b"cdn.example.com" in resp.data
