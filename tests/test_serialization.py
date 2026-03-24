import pytest
from flask import Flask
from pydantic import BaseModel

from flask_pydantic.serialization import serialize_response


class UserResponse(BaseModel):
    id: int
    name: str


@pytest.fixture
def app():
    app = Flask("test")
    app.config["TESTING"] = True
    return app


class TestSerializeResponse:
    def test_single_model(self, app):
        with app.app_context():
            model = UserResponse(id=1, name="Jane")
            response = serialize_response(model, status_code=200)
            assert response.status_code == 200
            assert response.json["id"] == 1
            assert response.json["name"] == "Jane"
            assert "application/json" in response.content_type

    def test_list_of_models(self, app):
        with app.app_context():
            models = [
                UserResponse(id=1, name="Jane"),
                UserResponse(id=2, name="John"),
            ]
            response = serialize_response(models, status_code=200, many=True)
            assert response.status_code == 200
            assert len(response.json) == 2

    def test_none_with_status(self, app):
        with app.app_context():
            response = serialize_response(None, status_code=204)
            assert response.status_code == 204
            assert response.data == b""

    def test_dict_passthrough(self, app):
        with app.app_context():
            response = serialize_response({"key": "val"}, status_code=200)
            assert response.status_code == 200
            assert response.json["key"] == "val"

    def test_tuple_model_status(self, app):
        with app.app_context():
            model = UserResponse(id=1, name="Jane")
            response = serialize_response((model, 201), status_code=200)
            assert response.status_code == 201
            assert response.json["id"] == 1

    def test_tuple_model_status_headers(self, app):
        with app.app_context():
            model = UserResponse(id=1, name="Jane")
            response = serialize_response(
                (model, 201, {"X-Custom": "yes"}), status_code=200
            )
            assert response.status_code == 201
            assert response.headers["X-Custom"] == "yes"

    def test_flask_response_passthrough(self, app):
        with app.app_context():
            from flask import make_response as flask_make_response
            original = flask_make_response("raw", 200)
            response = serialize_response(original, status_code=200)
            assert response is original
