"""End-to-end integration test: register routes, validate requests, check OpenAPI spec."""
from typing import Annotated, Optional

import pytest
from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel, Field

from flask_pydantic import FlaskPydantic, Body, Query, Status, docs
from flask_pydantic.markers import Form


class CreateItem(BaseModel):
    """Create an item."""
    name: str = Field(description="Item name", examples=["Widget"])
    price: float = Field(description="Item price")


class ItemQuery(BaseModel):
    limit: int = 10
    category: Optional[str] = None


class ItemResponse(BaseModel):
    id: int
    name: str
    price: float


class ErrorResponse(BaseModel):
    detail: str


@pytest.fixture
def full_app():
    app = Flask("integration_test")
    app.config["TESTING"] = True

    @app.route("/items", methods=["POST"])
    @docs(tag="Items", summary="Create item", errors={409: ErrorResponse})
    def create_item(body: Annotated[CreateItem, Body]) -> Annotated[ItemResponse, Status(201)]:
        """Create a new item in the catalog."""
        return ItemResponse(id=1, name=body.name, price=body.price)

    @app.route("/items", methods=["GET"])
    @docs(tag="Items")
    def list_items(query: Annotated[ItemQuery, Query]) -> list[ItemResponse]:
        return [ItemResponse(id=1, name="Widget", price=9.99)]

    @app.route("/health")
    def health() -> dict:
        return {"status": "ok"}

    class ItemDetailView(MethodView):
        errors = {404: ErrorResponse}

        def get(self, item_id: int) -> ItemResponse:
            """Get item by ID."""
            return ItemResponse(id=item_id, name="Widget", price=9.99)

        def delete(self, item_id: int) -> Annotated[None, Status(204)]:
            """Delete item."""
            return None

    app.add_url_rule(
        "/items/<int:item_id>",
        view_func=ItemDetailView.as_view("item_detail"),
    )

    FlaskPydantic(app)
    return app


@pytest.fixture
def client(full_app):
    return full_app.test_client()


class TestRequestValidation:
    def test_valid_post(self, client):
        resp = client.post("/items", json={"name": "Widget", "price": 9.99})
        assert resp.status_code == 201
        assert resp.json["name"] == "Widget"

    def test_invalid_post(self, client):
        resp = client.post("/items", json={"name": "Widget"})
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "body_params" in resp.json["validation_error"]

    def test_query_defaults(self, client):
        resp = client.get("/items")
        assert resp.status_code == 200
        assert isinstance(resp.json, list)

    def test_path_param(self, client):
        resp = client.get("/items/42")
        assert resp.status_code == 200
        assert resp.json["id"] == 42

    def test_delete_204(self, client):
        resp = client.delete("/items/1")
        assert resp.status_code == 204
        assert resp.data == b""

    def test_dict_passthrough(self, client):
        resp = client.get("/health")
        assert resp.json == {"status": "ok"}


class TestOpenAPISpec:
    def test_full_spec(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json

        assert spec["openapi"] == "3.1.0"
        assert "/items" in spec["paths"]
        assert "/items/{item_id}" in spec["paths"]

        # POST /items
        post_op = spec["paths"]["/items"]["post"]
        assert post_op["summary"] == "Create item"
        assert "requestBody" in post_op
        assert "201" in post_op["responses"]
        assert "409" in post_op["responses"]
        assert "422" in post_op["responses"]

        # GET /items
        get_op = spec["paths"]["/items"]["get"]
        param_names = [p["name"] for p in get_op.get("parameters", [])]
        assert "limit" in param_names

        # GET /items/{item_id}
        detail_get = spec["paths"]["/items/{item_id}"]["get"]
        assert "404" in detail_get["responses"]

        # DELETE /items/{item_id}
        detail_del = spec["paths"]["/items/{item_id}"]["delete"]
        assert "204" in detail_del["responses"]

        # Schemas
        assert "CreateItem" in spec["components"]["schemas"]
        assert "ItemResponse" in spec["components"]["schemas"]


class TestDocEndpoints:
    def test_swagger_ui(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert b"swagger-ui" in resp.data

    def test_redoc(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert b"redoc" in resp.data.lower()
