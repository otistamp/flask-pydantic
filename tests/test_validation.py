from typing import Annotated, Optional

import pytest
from flask import Flask
from pydantic import BaseModel

from flask_pydantic.markers import Body, Query, Form
from flask_pydantic.validation import validate_body, validate_query, validate_form, validate_path_param


class CreateUser(BaseModel):
    name: str
    email: str


class UserQuery(BaseModel):
    limit: int = 10
    offset: Optional[int] = None


class UserForm(BaseModel):
    name: str


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True
    return app


class TestValidateBody:
    def test_valid_json(self, app):
        with app.test_request_context(json={"name": "Jane", "email": "jane@example.com"}):
            result, errors = validate_body(CreateUser)
            assert result is not None
            assert result.name == "Jane"
            assert errors is None

    def test_invalid_json(self, app):
        with app.test_request_context(json={"name": "Jane"}):
            result, errors = validate_body(CreateUser)
            assert result is None
            assert errors is not None
            assert len(errors) > 0


class TestValidateQuery:
    def test_valid_query(self, app):
        with app.test_request_context("/?limit=5&offset=10"):
            result, errors = validate_query(UserQuery)
            assert result.limit == 5
            assert result.offset == 10
            assert errors is None

    def test_defaults(self, app):
        with app.test_request_context("/"):
            result, errors = validate_query(UserQuery)
            assert result.limit == 10
            assert errors is None

    def test_invalid_query(self, app):
        with app.test_request_context("/?limit=abc"):
            result, errors = validate_query(UserQuery)
            assert result is None
            assert errors is not None


class TestValidateForm:
    def test_valid_form(self, app):
        with app.test_request_context(
            method="POST", data={"name": "Jane"},
            content_type="application/x-www-form-urlencoded",
        ):
            result, errors = validate_form(UserForm)
            assert result.name == "Jane"
            assert errors is None

    def test_invalid_form(self, app):
        with app.test_request_context(
            method="POST", data={},
            content_type="application/x-www-form-urlencoded",
        ):
            result, errors = validate_form(UserForm)
            assert result is None
            assert errors is not None


class TestValidatePathParam:
    def test_valid_int(self):
        val, error = validate_path_param("user_id", "42", int)
        assert val == 42
        assert error is None

    def test_invalid_int(self):
        val, error = validate_path_param("user_id", "abc", int)
        assert val is None
        assert error is not None
