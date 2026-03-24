"""Tests for the @validate backwards-compatibility shim."""
import asyncio
import re
from typing import List, Optional

import pytest
from flask import Flask, request
from pydantic import BaseModel, ConfigDict, RootModel, field_validator, model_validator

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


# ---------------------------------------------------------------------------
# Edge case models
# ---------------------------------------------------------------------------


class ArrayModel(BaseModel):
    arr1: List[str]
    arr2: Optional[List[int]] = None


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


class ResultModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    result_of_addition: int
    result_of_multiplication: int


class Person(BaseModel):
    name: str
    age: int


class PersonBulk(RootModel):
    root: List[Person]


class ValidatedModel(BaseModel):
    name: str
    age: int

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @model_validator(mode="after")
    def age_must_be_positive(self):
        if self.age < 0:
            raise ValueError("age must be positive")
        return self


# ---------------------------------------------------------------------------
# 1. Array query params
# ---------------------------------------------------------------------------


@pytest.fixture
def array_app():
    app = Flask("test_array")
    app.config["TESTING"] = True

    @app.route("/array", methods=["GET"])
    @validate(query=ArrayModel, exclude_none=True)
    def array_route():
        q = request.query_params
        return {"arr1": q.arr1, "arr2": q.arr2}

    FlaskPydantic(app)
    return app


@pytest.fixture
def array_client(array_app):
    return array_app.test_client()


class TestArrayQueryParams:
    def test_multiple_values(self, array_client):
        resp = array_client.get("/array?arr1=first&arr1=second")
        assert resp.status_code == 200
        assert resp.json["arr1"] == ["first", "second"]
        # arr2 is excluded because exclude_none is set and route returns dict
        # but exclude_none only applies to BaseModel serialization, so arr2 may be None
        assert resp.json.get("arr2") is None

    def test_single_value(self, array_client):
        resp = array_client.get("/array?arr1=only")
        assert resp.status_code == 200
        assert resp.json["arr1"] == ["only"]

    def test_both_arrays(self, array_client):
        resp = array_client.get("/array?arr1=a&arr1=b&arr2=1&arr2=2")
        assert resp.status_code == 200
        assert resp.json == {"arr1": ["a", "b"], "arr2": [1, 2]}

    def test_missing_required_array(self, array_client):
        resp = array_client.get("/array")
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "query_params" in resp.json["validation_error"]


# ---------------------------------------------------------------------------
# 2. Response by alias (camel case)
# ---------------------------------------------------------------------------


@pytest.fixture
def alias_app():
    app = Flask("test_alias")
    app.config["TESTING"] = True

    @app.route("/alias", methods=["GET"])
    @validate(response_by_alias=True)
    def alias_route(query: QueryModel):
        return ResultModel(
            result_of_addition=query.limit + 3,
            result_of_multiplication=query.limit * 3,
        )

    FlaskPydantic(app)
    return app


@pytest.fixture
def alias_client(alias_app):
    return alias_app.test_client()


class TestResponseByAlias:
    def test_camel_case_keys(self, alias_client):
        resp = alias_client.get("/alias?limit=5")
        assert resp.status_code == 200
        data = resp.json
        assert "resultOfAddition" in data
        assert "resultOfMultiplication" in data
        assert data["resultOfAddition"] == 8
        assert data["resultOfMultiplication"] == 15


# ---------------------------------------------------------------------------
# 3. Async route
# ---------------------------------------------------------------------------


@pytest.fixture
def async_app():
    app = Flask("test_async")
    app.config["TESTING"] = True

    @app.route("/async", methods=["POST"])
    @validate()
    async def async_route(body: BodyModel):
        return ResponseModel(id=99, name=body.name, nickname=body.nickname)

    FlaskPydantic(app)
    return app


@pytest.fixture
def async_client(async_app):
    return async_app.test_client()


class TestAsyncRoute:
    def test_valid_async(self, async_client):
        resp = async_client.post("/async", json={"name": "Async Jane"})
        assert resp.status_code == 200
        assert resp.json["name"] == "Async Jane"
        assert resp.json["id"] == 99

    def test_invalid_async(self, async_client):
        resp = async_client.post("/async", json={})
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "body_params" in resp.json["validation_error"]


# ---------------------------------------------------------------------------
# 4. Path params
# ---------------------------------------------------------------------------


@pytest.fixture
def path_app():
    app = Flask("test_path")
    app.config["TESTING"] = True

    @app.route("/items/<obj_id>", methods=["GET"])
    @validate()
    def item_route(obj_id: int):
        return {"item_id": obj_id}

    FlaskPydantic(app)
    return app


@pytest.fixture
def path_client(path_app):
    return path_app.test_client()


class TestPathParams:
    def test_valid_path_param(self, path_client):
        resp = path_client.get("/items/42")
        assert resp.status_code == 200
        assert resp.json["item_id"] == 42

    def test_invalid_path_param(self, path_client):
        resp = path_client.get("/items/not_a_number")
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "path_params" in resp.json["validation_error"]


# ---------------------------------------------------------------------------
# 5. Custom root type (RootModel)
# ---------------------------------------------------------------------------


@pytest.fixture
def root_app():
    app = Flask("test_root")
    app.config["TESTING"] = True

    @app.route("/bulk", methods=["POST"])
    @validate()
    def bulk_route(body: PersonBulk):
        return {"count": len(body.root)}

    FlaskPydantic(app)
    return app


@pytest.fixture
def root_client(root_app):
    return root_app.test_client()


class TestRootModel:
    def test_bulk_post(self, root_client):
        payload = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        resp = root_client.post("/bulk", json=payload)
        assert resp.status_code == 200
        assert resp.json["count"] == 2


# ---------------------------------------------------------------------------
# 6. Tuple returns with custom headers
# ---------------------------------------------------------------------------


@pytest.fixture
def header_app():
    app = Flask("test_headers")
    app.config["TESTING"] = True

    @app.route("/header-only", methods=["GET"])
    @validate()
    def header_only():
        return ResponseModel(id=1, name="test"), {"CUSTOM_HEADER": "UNIQUE"}

    @app.route("/header-status", methods=["GET"])
    @validate()
    def header_and_status():
        return ResponseModel(id=1, name="test"), 201, {"CUSTOM_HEADER": "UNIQUE"}

    FlaskPydantic(app)
    return app


@pytest.fixture
def header_client(header_app):
    return header_app.test_client()


class TestTupleReturnWithHeaders:
    def test_model_with_headers(self, header_client):
        resp = header_client.get("/header-only")
        assert resp.status_code == 200
        assert resp.json["id"] == 1
        assert resp.headers.get("CUSTOM_HEADER") == "UNIQUE"

    def test_model_with_status_and_headers(self, header_client):
        resp = header_client.get("/header-status")
        assert resp.status_code == 201
        assert resp.json["id"] == 1
        assert resp.headers.get("CUSTOM_HEADER") == "UNIQUE"


# ---------------------------------------------------------------------------
# 7. Field and model validators
# ---------------------------------------------------------------------------


@pytest.fixture
def validator_app():
    app = Flask("test_validators")
    app.config["TESTING"] = True

    @app.route("/validated", methods=["POST"])
    @validate()
    def validated_route(body: ValidatedModel):
        return {"name": body.name, "age": body.age}

    FlaskPydantic(app)
    return app


@pytest.fixture
def validator_client(validator_app):
    return validator_app.test_client()


class TestFieldAndModelValidators:
    def test_field_validator_error(self, validator_client):
        resp = validator_client.post("/validated", json={"name": "  ", "age": 10})
        assert resp.status_code == 422
        errors = resp.json["validation_error"]["body_params"]
        name_errors = [e for e in errors if "name" in e.get("loc", [])]
        assert len(name_errors) > 0
        # ctx should have serialized exception info
        ctx = name_errors[0].get("ctx", {})
        assert "error" in ctx
        assert ctx["error"]["type"] == "ValueError"
        assert "empty" in ctx["error"]["message"]

    def test_model_validator_error(self, validator_client):
        resp = validator_client.post("/validated", json={"name": "Alice", "age": -1})
        assert resp.status_code == 422
        errors = resp.json["validation_error"]["body_params"]
        # model_validator errors may have different loc but ctx should be serialized
        found = False
        for e in errors:
            ctx = e.get("ctx", {})
            if isinstance(ctx.get("error"), dict) and "positive" in ctx["error"].get("message", ""):
                found = True
                break
        assert found, f"Expected model validator error with 'positive' message, got: {errors}"

    def test_valid_passes(self, validator_client):
        resp = validator_client.post("/validated", json={"name": "Alice", "age": 25})
        assert resp.status_code == 200
        assert resp.json == {"name": "Alice", "age": 25}


# ---------------------------------------------------------------------------
# 8. get_json_params silent mode
# ---------------------------------------------------------------------------


@pytest.fixture
def silent_app():
    app = Flask("test_silent")
    app.config["TESTING"] = True

    @app.route("/silent", methods=["POST"])
    @validate(body=BodyModel, get_json_params={"silent": True})
    def silent_route():
        return ResponseModel(id=1, name=request.body_params.name)

    FlaskPydantic(app)
    return app


@pytest.fixture
def silent_client(silent_app):
    return silent_app.test_client()


class TestGetJsonParamsSilent:
    def test_empty_body_with_json_content_type(self, silent_client):
        resp = silent_client.post(
            "/silent",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 422
        assert "validation_error" in resp.json
        assert "body_params" in resp.json["validation_error"]
