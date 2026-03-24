from functools import wraps
from typing import List

import pytest
from flask import Blueprint, Flask
from flask_pydantic import api, generate_openapi_spec
from pydantic import BaseModel


class UserQuery(BaseModel):
    limit: int = 10
    offset: int = 0


class CreateUser(BaseModel):
    name: str
    email: str


class UserResponse(BaseModel):
    id: int
    name: str


class ErrorResponse(BaseModel):
    """Not found error."""

    detail: str


class FormModel(BaseModel):
    username: str
    password: str


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


# ---------------------------------------------------------------------------
# Task 6: Query / body / form / response schema extraction tests
# ---------------------------------------------------------------------------


class TestQueryParamsInSpec:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users")
        @api()
        def list_users(query: UserQuery) -> List[UserResponse]:
            pass

        return app

    def test_query_params_in_parameters(self, app):
        spec = generate_openapi_spec(app)
        params = spec["paths"]["/users"]["get"]["parameters"]
        query_params = [p for p in params if p["in"] == "query"]
        assert len(query_params) == 2
        names = {p["name"] for p in query_params}
        assert names == {"limit", "offset"}

    def test_query_param_not_required_when_has_default(self, app):
        spec = generate_openapi_spec(app)
        params = spec["paths"]["/users"]["get"]["parameters"]
        for p in params:
            if p["in"] == "query":
                assert p["required"] is False


class TestBodyInSpec:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users", methods=["POST"])
        @api()
        def create_user(body: CreateUser) -> UserResponse:
            pass

        return app

    def test_request_body_present(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/users"]["post"]
        assert "requestBody" in op
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert "name" in schema["properties"]
        assert "email" in schema["properties"]

    def test_response_schema(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/users"]["post"]
        resp_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert "id" in resp_schema["properties"]
        assert "name" in resp_schema["properties"]


class TestFormInSpec:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/login", methods=["POST"])
        @api()
        def login(form: FormModel):
            pass

        return app

    def test_form_body_present(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/login"]["post"]
        assert "requestBody" in op
        assert "multipart/form-data" in op["requestBody"]["content"]


class TestErrorResponses:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users/<int:user_id>")
        @api(response=UserResponse, errors={404: ErrorResponse})
        def get_user(user_id: int):
            pass

        return app

    def test_error_response_included(self, app):
        spec = generate_openapi_spec(app)
        responses = spec["paths"]["/users/{user_id}"]["get"]["responses"]
        assert "404" in responses
        schema = responses["404"]["content"]["application/json"]["schema"]
        assert "detail" in schema["properties"]

    def test_success_response_included(self, app):
        spec = generate_openapi_spec(app)
        responses = spec["paths"]["/users/{user_id}"]["get"]["responses"]
        assert "200" in responses

    def test_validation_error_included(self, app):
        spec = generate_openapi_spec(app)
        responses = spec["paths"]["/users/{user_id}"]["get"]["responses"]
        assert "400" in responses


class TestResponseMany:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users")
        @api(response=UserResponse, response_many=True)
        def list_users():
            pass

        return app

    def test_response_many_produces_array_schema(self, app):
        spec = generate_openapi_spec(app)
        resp = spec["paths"]["/users"]["get"]["responses"]["200"]
        schema = resp["content"]["application/json"]["schema"]
        assert schema["type"] == "array"
        assert "properties" in schema["items"]


class TestRequestBodyMany:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users/bulk", methods=["POST"])
        @api(body=CreateUser, request_body_many=True)
        def bulk_create():
            pass

        return app

    def test_request_body_many_produces_array_schema(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/users/bulk"]["post"]
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert schema["type"] == "array"
        assert "properties" in schema["items"]


# ---------------------------------------------------------------------------
# Task 7: Path params, blueprints, docstrings, operationId tests
# ---------------------------------------------------------------------------


class TestPathParams:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/users/<int:user_id>")
        @api(response=UserResponse)
        def get_user(user_id: int):
            pass

        @app.route("/files/<path:filepath>")
        @api(validate=False)
        def get_file(filepath: str):
            pass

        return app

    def test_path_param_integer(self, app):
        spec = generate_openapi_spec(app)
        params = spec["paths"]["/users/{user_id}"]["get"]["parameters"]
        path_params = [p for p in params if p["in"] == "path"]
        assert len(path_params) == 1
        assert path_params[0]["name"] == "user_id"
        assert path_params[0]["schema"]["type"] == "integer"
        assert path_params[0]["required"] is True

    def test_path_param_path_type(self, app):
        spec = generate_openapi_spec(app)
        params = spec["paths"]["/files/{filepath}"]["get"]["parameters"]
        path_params = [p for p in params if p["in"] == "path"]
        assert path_params[0]["schema"]["type"] == "string"


class TestBlueprintTags:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True
        bp = Blueprint("users", __name__)

        @bp.route("/")
        @api(validate=False)
        def list_users():
            pass

        app.register_blueprint(bp, url_prefix="/users")
        return app

    def test_blueprint_name_as_tag(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/users/"]["get"]
        assert "tags" in op
        assert "users" in op["tags"]


class TestDocstrings:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/test")
        @api(validate=False)
        def documented_route():
            """Get the test resource.

            This endpoint returns a test resource
            for demonstration purposes.
            """
            pass

        @app.route("/no-doc")
        @api(validate=False)
        def undocumented_route():
            pass

        return app

    def test_summary_from_first_line(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/test"]["get"]
        assert op["summary"] == "Get the test resource."

    def test_description_from_remaining_lines(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/test"]["get"]
        assert "demonstration purposes" in op["description"]

    def test_no_docstring_no_summary(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/no-doc"]["get"]
        assert "summary" not in op
        assert "description" not in op


class TestOperationId:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/test")
        @api(validate=False)
        def my_endpoint():
            pass

        return app

    def test_operation_id_from_endpoint(self, app):
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/test"]["get"]
        assert op["operationId"] == "my_endpoint"

    def test_blueprint_operation_id(self):
        app = Flask("test")
        app.config["TESTING"] = True
        bp = Blueprint("v1", __name__)

        @bp.route("/items")
        @api(validate=False)
        def list_items():
            pass

        app.register_blueprint(bp, url_prefix="/v1")
        spec = generate_openapi_spec(app)
        op = spec["paths"]["/v1/items"]["get"]
        assert op["operationId"] == "v1.list_items"


class TestValidateFalseNoValidationError:
    @pytest.fixture
    def app(self):
        app = Flask("test")
        app.config["TESTING"] = True

        @app.route("/test")
        @api(validate=False)
        def test_route():
            pass

        return app

    def test_no_400_when_validate_false(self, app):
        spec = generate_openapi_spec(app)
        responses = spec["paths"]["/test"]["get"]["responses"]
        assert "400" not in responses


# ---------------------------------------------------------------------------
# Task 8: __wrapped__ chain traversal test
# ---------------------------------------------------------------------------


class TestWrappedChainTraversal:
    def test_metadata_found_through_wrapped_chain(self):
        app = Flask("test")
        app.config["TESTING"] = True

        def my_decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                return f(*args, **kwargs)

            return decorated

        @app.route("/test")
        @my_decorator
        @api(validate=False)
        def test_route():
            """A wrapped route."""
            pass

        spec = generate_openapi_spec(app)
        assert "/test" in spec["paths"]
        assert spec["paths"]["/test"]["get"]["summary"] == "A wrapped route."
