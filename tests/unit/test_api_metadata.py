from typing import List, Optional

import pytest
from flask import Flask
from flask_pydantic import api, validate
from pydantic import BaseModel


class QueryModel(BaseModel):
    q: str


class BodyModel(BaseModel):
    name: str


class TestApiMetadata:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True
        return app

    def test_api_stores_metadata(self, app):
        @app.route("/test")
        @api()
        def test_route(query: QueryModel):
            pass

        view_func = app.view_functions["test_route"]
        assert hasattr(view_func, "_api_metadata")
        meta = view_func._api_metadata
        assert meta["query_model"] is QueryModel
        assert meta["body_model"] is None
        assert meta["form_model"] is None
        assert meta["response_model"] is None
        assert meta["errors"] is None
        assert meta["validate"] is True
        assert meta["on_success_status"] == 200
        assert meta["response_many"] is False
        assert meta["request_body_many"] is False

    def test_api_stores_explicit_models(self, app):
        @app.route("/test")
        @api(query=QueryModel, body=BodyModel)
        def test_route():
            pass

        view_func = app.view_functions["test_route"]
        meta = view_func._api_metadata
        assert meta["query_model"] is QueryModel
        assert meta["body_model"] is BodyModel

    def test_validate_alias_stores_metadata(self, app):
        @app.route("/test")
        @validate()
        def test_route(query: QueryModel):
            pass

        view_func = app.view_functions["test_route"]
        assert hasattr(view_func, "_api_metadata")
        meta = view_func._api_metadata
        assert meta["query_model"] is QueryModel

    def test_validate_false_skips_validation(self, app):
        """When validate=False, no validation occurs even with invalid data."""

        @app.route("/test", methods=["POST"])
        @api(validate=False)
        def test_route(body: BodyModel):
            return {"ok": True}

        with app.test_client() as client:
            resp = client.post("/test", json={})
            assert resp.status_code == 200

    def test_validate_false_stores_metadata(self, app):
        @app.route("/test")
        @api(validate=False)
        def test_route(query: QueryModel):
            pass

        view_func = app.view_functions["test_route"]
        meta = view_func._api_metadata
        assert meta["validate"] is False
        assert meta["query_model"] is QueryModel

    def test_config_override_default(self, app):
        """app.config FLASK_PYDANTIC_VALIDATE overrides default when not explicitly passed."""
        app.config["FLASK_PYDANTIC_VALIDATE"] = False

        @app.route("/test", methods=["POST"])
        @api()
        def test_route(body: BodyModel):
            return {"ok": True}

        with app.test_client() as client:
            resp = client.post("/test", json={})
            assert resp.status_code == 200

    def test_explicit_validate_overrides_config(self, app):
        """Explicit validate=True overrides config setting of False."""
        app.config["FLASK_PYDANTIC_VALIDATE"] = False

        @app.route("/test", methods=["POST"])
        @api(validate=True)
        def test_route(body: BodyModel):
            return {"ok": True}

        with app.test_client() as client:
            resp = client.post("/test", json={})
            assert resp.status_code == 400


class ResponseModel(BaseModel):
    id: int
    name: str


class ErrorModel(BaseModel):
    detail: str


class TestResponseModelResolution:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True
        return app

    def test_explicit_response_param(self, app):
        @app.route("/test")
        @api(response=ResponseModel)
        def test_route():
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is ResponseModel

    def test_return_type_hint_fallback(self, app):
        @app.route("/test")
        @api()
        def test_route() -> ResponseModel:
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is ResponseModel

    def test_explicit_response_overrides_hint(self, app):
        @app.route("/test")
        @api(response=ErrorModel)
        def test_route() -> ResponseModel:
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is ErrorModel

    def test_list_return_type_unwrapped(self, app):
        @app.route("/test")
        @api()
        def test_route() -> List[ResponseModel]:
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is ResponseModel

    def test_optional_return_type_unwrapped(self, app):
        @app.route("/test")
        @api()
        def test_route() -> Optional[ResponseModel]:
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is ResponseModel

    def test_non_model_return_type_ignored(self, app):
        @app.route("/test")
        @api()
        def test_route() -> dict:
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is None

    def test_no_return_type_no_response(self, app):
        @app.route("/test")
        @api()
        def test_route():
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["response_model"] is None

    def test_errors_stored(self, app):
        @app.route("/test")
        @api(errors={404: ErrorModel, 422: ErrorModel})
        def test_route():
            pass

        meta = app.view_functions["test_route"]._api_metadata
        assert meta["errors"] == {404: ErrorModel, 422: ErrorModel}
