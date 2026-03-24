# Flask-Pydantic v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flask-pydantic's `@validate` decorator with a Flask extension that uses `Annotated` type hints for request/response modeling and auto-generates OpenAPI 3.1 specs with Swagger UI and ReDoc endpoints.

**Architecture:** A `FlaskPydantic` extension wraps view functions at registration time, inspecting type hints to extract `Body`, `Query`, `Form`, `Status` markers. A validation layer parses/validates request data and serializes responses. A separate OpenAPI module introspects the same metadata to generate the spec lazily on first docs request.

**Tech Stack:** Flask, Pydantic v2, PyYAML (optional)

**Spec:** `docs/superpowers/specs/2026-03-23-flask-pydantic-v2-design.md`

---

## File Structure

```
flask_pydantic/
    __init__.py          # Public API: FlaskPydantic, Body, Query, Form, Status, docs
    markers.py           # Body, Query, Form, Status marker/sentinel classes
    inspection.py        # Extract parameter metadata from type hints + route rules
    validation.py        # Parse request data into validated Pydantic models
    serialization.py     # Serialize BaseModel responses to JSON Flask Responses
    extension.py         # FlaskPydantic class: init_app, view wrapping, config
    openapi.py           # Generate OpenAPI 3.1 spec dict from route metadata
    docs_views.py        # Blueprint with /openapi.json, /openapi.yaml, /docs, /redoc
    exceptions.py        # Exception classes (keep + adapt from v1)
    version.py           # Version string (bump to 2.0.0)
tests/
    test_markers.py      # Unit tests for marker classes
    test_inspection.py   # Unit tests for type hint introspection
    test_validation.py   # Unit tests for request parsing/validation
    test_serialization.py # Unit tests for response serialization
    test_extension.py    # Integration tests for FlaskPydantic extension
    test_openapi.py      # Unit tests for OpenAPI spec generation
    test_docs_views.py   # Integration tests for doc endpoints
    test_method_view.py  # Integration tests for MethodView support
    conftest.py          # Shared fixtures
```

---

### Task 1: Markers Module

**Files:**
- Create: `flask_pydantic/markers.py`
- Create: `tests/test_markers.py`

- [ ] **Step 1: Write failing tests for markers**

```python
# tests/test_markers.py
from typing import Annotated, get_type_hints

from pydantic import BaseModel

from flask_pydantic.markers import Body, Form, Query, Status


class UserModel(BaseModel):
    name: str


def test_body_marker_is_sentinel():
    assert isinstance(Body, type) or callable(Body)


def test_query_marker_is_sentinel():
    assert isinstance(Query, type) or callable(Query)


def test_form_marker_is_sentinel():
    assert isinstance(Form, type) or callable(Form)


def test_status_stores_code():
    s = Status(201)
    assert s.code == 201


def test_status_default_is_200():
    s = Status()
    assert s.code == 200


def test_markers_usable_in_annotated():
    def example(body: Annotated[UserModel, Body]) -> Annotated[UserModel, Status(201)]:
        ...

    hints = get_type_hints(example, include_extras=True)
    assert hints["body"].__metadata__[0] is Body
    assert hints["return"].__metadata__[0].code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_markers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flask_pydantic.markers'`

- [ ] **Step 3: Implement markers**

```python
# flask_pydantic/markers.py


class _Marker:
    """Base sentinel for Annotated parameter markers."""
    pass


class Body(_Marker):
    """Marks a parameter as JSON request body."""
    pass


class Query(_Marker):
    """Marks a parameter as query string parameters."""
    pass


class Form(_Marker):
    """Marks a parameter as form-encoded body."""
    pass


class Status:
    """Annotates a return type with an HTTP status code."""
    __slots__ = ("code",)

    def __init__(self, code: int = 200):
        self.code = code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_markers.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flask_pydantic/markers.py tests/test_markers.py
git commit -m "feat: add Body, Query, Form, Status marker classes"
```

---

### Task 2: Inspection Module

**Files:**
- Create: `flask_pydantic/inspection.py`
- Create: `tests/test_inspection.py`

- [ ] **Step 1: Write failing tests for type hint introspection**

```python
# tests/test_inspection.py
from typing import Annotated, Optional

from pydantic import BaseModel

from flask_pydantic.inspection import extract_params, RouteParams
from flask_pydantic.markers import Body, Form, Query, Status


class CreateUser(BaseModel):
    name: str
    email: str


class UserQuery(BaseModel):
    age_min: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    name: str


class UserForm(BaseModel):
    name: str


def test_extract_body_and_query():
    def view(
        body: Annotated[CreateUser, Body],
        query: Annotated[UserQuery, Query],
    ) -> UserResponse:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.body_model is CreateUser
    assert params.body_param_name == "body"
    assert params.query_model is UserQuery
    assert params.query_param_name == "query"
    assert params.form_model is None
    assert params.response_model is UserResponse
    assert params.status_code == 200


def test_extract_status_code():
    def view(body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.status_code == 201
    assert params.response_model is UserResponse


def test_extract_path_params():
    def view(user_id: int) -> UserResponse:
        ...

    params = extract_params(view, path_param_names={"user_id"})
    assert params.path_params == {"user_id": int}


def test_extract_form():
    def view(form: Annotated[UserForm, Form]) -> UserResponse:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.form_model is UserForm
    assert params.form_param_name == "form"


def test_body_and_form_raises():
    def view(
        body: Annotated[CreateUser, Body],
        form: Annotated[UserForm, Form],
    ) -> UserResponse:
        ...

    import pytest
    with pytest.raises(ValueError, match="[Mm]utually exclusive"):
        extract_params(view, path_param_names=set())


def test_no_return_annotation():
    def view():
        ...

    params = extract_params(view, path_param_names=set())
    assert params.response_model is None
    assert params.status_code == 200


def test_none_return_with_status():
    def view() -> Annotated[None, Status(204)]:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.response_model is None
    assert params.status_code == 204


def test_list_response():
    def view() -> list[UserResponse]:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.response_model is UserResponse
    assert params.response_many is True


def test_dict_return():
    def view() -> dict:
        ...

    params = extract_params(view, path_param_names=set())
    assert params.response_model is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inspection.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement inspection module**

```python
# flask_pydantic/inspection.py
from dataclasses import dataclass, field
from typing import Any, Optional, Set, Type, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from .markers import Body, Form, Query, Status


@dataclass
class RouteParams:
    """Extracted parameter metadata for a single route/view function."""
    body_model: Optional[Type[BaseModel]] = None
    body_param_name: Optional[str] = None
    query_model: Optional[Type[BaseModel]] = None
    query_param_name: Optional[str] = None
    form_model: Optional[Type[BaseModel]] = None
    form_param_name: Optional[str] = None
    path_params: dict = field(default_factory=dict)
    response_model: Optional[Type[BaseModel]] = None
    response_many: bool = False
    status_code: int = 200


def _is_annotated(hint: Any) -> bool:
    return get_origin(hint) is not None and hasattr(hint, "__metadata__")


def _find_marker(hint: Any, marker_type: type) -> Any:
    """Search Annotated metadata for a marker instance or class."""
    if not _is_annotated(hint):
        return None
    for meta in hint.__metadata__:
        if meta is marker_type or isinstance(meta, marker_type):
            return meta
    return None


def extract_params(func, path_param_names: Set[str]) -> RouteParams:
    """Extract parameter and response metadata from a view function's type hints."""
    hints = get_type_hints(func, include_extras=True)
    params = RouteParams()

    return_hint = hints.pop("return", None)

    for name, hint in hints.items():
        if name in path_param_names:
            # Unwrap Annotated if present
            inner = get_args(hint)[0] if _is_annotated(hint) else hint
            params.path_params[name] = inner
            continue

        body_marker = _find_marker(hint, Body)
        if body_marker is not None:
            if params.form_model is not None:
                raise ValueError("Body and Form are mutually exclusive on the same route")
            params.body_model = get_args(hint)[0]
            params.body_param_name = name
            continue

        query_marker = _find_marker(hint, Query)
        if query_marker is not None:
            params.query_model = get_args(hint)[0]
            params.query_param_name = name
            continue

        form_marker = _find_marker(hint, Form)
        if form_marker is not None:
            if params.body_model is not None:
                raise ValueError("Body and Form are mutually exclusive on the same route")
            params.form_model = get_args(hint)[0]
            params.form_param_name = name
            continue

    # Parse return type
    if return_hint is not None:
        status_marker = _find_marker(return_hint, Status)
        if status_marker is not None:
            params.status_code = status_marker.code
            inner = get_args(return_hint)[0]
        else:
            inner = return_hint

        # Check for list[Model]
        origin = get_origin(inner)
        if origin is list:
            args = get_args(inner)
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                params.response_model = args[0]
                params.response_many = True
        elif inner is None or inner is type(None):
            params.response_model = None
        elif isinstance(inner, type) and issubclass(inner, BaseModel):
            params.response_model = inner
        # else: dict, Response, etc. — no schema

    return params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_inspection.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flask_pydantic/inspection.py tests/test_inspection.py
git commit -m "feat: add type hint introspection for route parameters"
```

---

### Task 3: Clean Up converters.py and Validation Module

**Files:**
- Modify: `flask_pydantic/converters.py` (remove Pydantic v1 code)
- Create: `flask_pydantic/validation.py`
- Create: `tests/test_validation.py`
- Modify: `flask_pydantic/exceptions.py`

- [ ] **Step 0: Clean converters.py — remove Pydantic v1 imports and branches**

Remove the `pydantic.v1` imports and the v1 branch in `convert_query_params`. The function should only support Pydantic v2 `BaseModel`:

```python
# flask_pydantic/converters.py
import types
from collections import deque
from typing import Deque, FrozenSet, List, Sequence, Set, Tuple, Type, Union

try:
    from typing import get_args, get_origin
except ImportError:
    from typing_extensions import get_args, get_origin

from pydantic import BaseModel
from werkzeug.datastructures import ImmutableMultiDict

UnionType = getattr(types, "UnionType", Union)

sequence_types = {
    Sequence, List, list, Tuple, tuple, Set, set, FrozenSet, frozenset, Deque, deque,
}


def _is_sequence(type_: Type) -> bool:
    origin = get_origin(type_) or type_
    if origin is Union or origin is UnionType:
        return any(_is_sequence(t) for t in get_args(type_))
    return origin in sequence_types and origin not in (str, bytes)


def convert_query_params(
    query_params: ImmutableMultiDict, model: Type[BaseModel]
) -> dict:
    return {
        **query_params.to_dict(),
        **{
            key: value
            for key, value in query_params.to_dict(flat=False).items()
            if key in model.model_fields
            and _is_sequence(model.model_fields[key].annotation)
        },
    }
```

- [ ] **Step 1: Write failing tests for validation**

```python
# tests/test_validation.py
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
        with app.test_request_context(
            json={"name": "Jane", "email": "jane@example.com"}
        ):
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
            method="POST",
            data={"name": "Jane"},
            content_type="application/x-www-form-urlencoded",
        ):
            result, errors = validate_form(UserForm)
            assert result.name == "Jane"
            assert errors is None

    def test_invalid_form(self, app):
        with app.test_request_context(
            method="POST",
            data={},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_validation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Update exceptions module**

```python
# flask_pydantic/exceptions.py
from typing import Dict, List, Optional


class FlaskPydanticError(Exception):
    """Base exception for flask-pydantic."""
    pass


class ValidationError(FlaskPydanticError):
    """Raised when request validation fails (if configured to raise)."""

    def __init__(
        self,
        body_params: Optional[List[dict]] = None,
        form_params: Optional[List[dict]] = None,
        path_params: Optional[List[dict]] = None,
        query_params: Optional[List[dict]] = None,
    ):
        super().__init__()
        self.body_params = body_params
        self.form_params = form_params
        self.path_params = path_params
        self.query_params = query_params
```

- [ ] **Step 4: Implement validation module**

```python
# flask_pydantic/validation.py
from typing import Any, List, Optional, Tuple, Type

from flask import request
from pydantic import BaseModel, TypeAdapter, ValidationError

from .converters import convert_query_params


def _sanitize_ctx_errors(errors: List[dict]) -> List[dict]:
    for error in errors:
        ctx = error.get("ctx")
        if isinstance(ctx, dict) and isinstance(ctx.get("error"), Exception):
            exc = ctx["error"]
            ctx["error"] = {"type": type(exc).__name__, "message": str(exc)}
    return errors


def validate_body(
    model: Type[BaseModel],
) -> Tuple[Optional[BaseModel], Optional[List[dict]]]:
    """Parse and validate JSON body. Returns (model, None) or (None, errors)."""
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    try:
        return model(**data), None
    except ValidationError as e:
        return None, _sanitize_ctx_errors(e.errors())


def validate_query(
    model: Type[BaseModel],
) -> Tuple[Optional[BaseModel], Optional[List[dict]]]:
    """Parse and validate query parameters. Returns (model, None) or (None, errors)."""
    query_params = convert_query_params(request.args, model)
    try:
        return model(**query_params), None
    except ValidationError as e:
        return None, _sanitize_ctx_errors(e.errors())


def validate_form(
    model: Type[BaseModel],
) -> Tuple[Optional[BaseModel], Optional[List[dict]]]:
    """Parse and validate form data. Returns (model, None) or (None, errors)."""
    try:
        return model(**request.form), None
    except ValidationError as e:
        return None, _sanitize_ctx_errors(e.errors())


def validate_path_param(
    name: str, value: Any, type_: type
) -> Tuple[Optional[Any], Optional[dict]]:
    """Validate a single path parameter. Returns (value, None) or (None, error)."""
    try:
        adapter = TypeAdapter(type_)
        return adapter.validate_python(value), None
    except ValidationError as e:
        err = e.errors()[0]
        err["loc"] = [name]
        return None, err
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_validation.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add flask_pydantic/validation.py flask_pydantic/exceptions.py tests/test_validation.py
git commit -m "feat: add request validation for body, query, form, and path params"
```

---

### Task 4: Serialization Module

**Files:**
- Create: `flask_pydantic/serialization.py`
- Create: `tests/test_serialization.py`

- [ ] **Step 1: Write failing tests for serialization**

```python
# tests/test_serialization.py
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
            assert response.content_type == "application/json"

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_serialization.py -v`
Expected: FAIL

- [ ] **Step 3: Implement serialization module**

```python
# flask_pydantic/serialization.py
from typing import Any

from flask import Response, jsonify, make_response
from pydantic import BaseModel


def serialize_response(result: Any, status_code: int, many: bool = False) -> Response:
    """Serialize a view function's return value into a Flask Response."""
    # Flask Response passthrough
    if isinstance(result, Response):
        return result

    # None → empty response
    if result is None:
        return make_response("", status_code)

    # Tuple unpacking: (body, status) or (body, status, headers)
    if isinstance(result, tuple):
        headers = None
        if len(result) == 2:
            body, status_code = result
        elif len(result) == 3:
            body, status_code, headers = result
        else:
            return make_response(result, status_code)
        resp = serialize_response(body, status_code, many=many)
        if headers:
            resp.headers.update(headers)
        return resp

    # List of models
    if many and isinstance(result, list):
        js = "[" + ", ".join(m.model_dump_json() for m in result) + "]"
        response = make_response(js, status_code)
        response.mimetype = "application/json"
        return response

    # Single BaseModel
    if isinstance(result, BaseModel):
        response = make_response(result.model_dump_json(), status_code)
        response.mimetype = "application/json"
        return response

    # dict or other — jsonify
    if isinstance(result, dict):
        return make_response(jsonify(result), status_code)

    # Fallback
    return make_response(result, status_code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_serialization.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flask_pydantic/serialization.py tests/test_serialization.py
git commit -m "feat: add response serialization with model/tuple/dict handling"
```

---

### Task 5: `@docs()` Decorator

**Files:**
- Create: `flask_pydantic/docs_decorator.py`
- Create: `tests/test_docs_decorator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docs_decorator.py
from flask_pydantic.docs_decorator import docs
from pydantic import BaseModel


class NotFoundError(BaseModel):
    detail: str


def test_docs_stores_metadata():
    @docs(tag="Users", summary="Get user", description="Gets a user by ID")
    def get_user():
        ...

    meta = get_user._pydantic_docs
    assert meta["tag"] == "Users"
    assert meta["summary"] == "Get user"
    assert meta["description"] == "Gets a user by ID"


def test_docs_stores_errors():
    @docs(errors={404: NotFoundError})
    def get_user():
        ...

    assert get_user._pydantic_docs["errors"] == {404: NotFoundError}


def test_docs_deprecated():
    @docs(deprecated=True)
    def old_endpoint():
        ...

    assert old_endpoint._pydantic_docs["deprecated"] is True


def test_docs_operation_id():
    @docs(operation_id="getUser")
    def get_user():
        ...

    assert get_user._pydantic_docs["operation_id"] == "getUser"


def test_docs_validate_false():
    @docs(validate=False)
    def get_user():
        ...

    assert get_user._pydantic_docs["validate"] is False


def test_no_docs_has_no_attribute():
    def plain():
        ...

    assert not hasattr(plain, "_pydantic_docs")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_docs_decorator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `@docs()` decorator**

```python
# flask_pydantic/docs_decorator.py
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel


def docs(
    tag: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    operation_id: Optional[str] = None,
    errors: Optional[Dict[int, Type[BaseModel]]] = None,
    validate: Optional[bool] = None,
) -> Callable:
    """Attach OpenAPI metadata to a view function."""
    def decorator(func: Callable) -> Callable:
        meta = {}
        if tag is not None:
            meta["tag"] = tag
        if summary is not None:
            meta["summary"] = summary
        if description is not None:
            meta["description"] = description
        if deprecated:
            meta["deprecated"] = True
        if operation_id is not None:
            meta["operation_id"] = operation_id
        if errors is not None:
            meta["errors"] = errors
        if validate is not None:
            meta["validate"] = validate
        func._pydantic_docs = meta
        return func
    return decorator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_docs_decorator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flask_pydantic/docs_decorator.py tests/test_docs_decorator.py
git commit -m "feat: add @docs() decorator for OpenAPI metadata"
```

---

### Task 6: Extension Core (FlaskPydantic + View Wrapping)

**Files:**
- Create: `flask_pydantic/extension.py`
- Create: `tests/test_extension.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/test_extension.py
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
            "/submit",
            data={"name": "Jane"},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 200
        assert resp.json["name"] == "Jane"

    def test_invalid_form(self, form_client):
        resp = form_client.post(
            "/submit",
            data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 422
        assert "validation_error" in resp.json
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extension.py -v`
Expected: FAIL

- [ ] **Step 3: Implement extension module**

```python
# flask_pydantic/extension.py
from functools import wraps
from typing import Any, Callable, Set

from flask import Flask, current_app, jsonify, make_response
from pydantic import BaseModel

from .inspection import RouteParams, extract_params
from .serialization import serialize_response
from .validation import validate_body, validate_form, validate_path_param, validate_query


def _get_path_param_names(rule) -> Set[str]:
    """Extract path parameter names from a werkzeug Rule."""
    return {arg for arg in rule.arguments}


def _get_docs_meta(func: Callable) -> dict:
    """Get @docs() metadata from a function, if present."""
    return getattr(func, "_pydantic_docs", {})


def _should_validate(func: Callable, app: Flask) -> bool:
    """Check if validation is enabled for this route."""
    docs_meta = _get_docs_meta(func)
    if "validate" in docs_meta:
        return docs_meta["validate"]
    return app.config.get("FLASK_PYDANTIC_VALIDATE", True)


def _wrap_view(func: Callable, rule, app: Flask) -> Callable:
    """Wrap a view function with validation and serialization."""
    path_param_names = _get_path_param_names(rule)

    try:
        params = extract_params(func, path_param_names)
    except (TypeError, ValueError):
        # No usable type hints — skip wrapping
        return func

    # Nothing to wrap if no markers and no response model
    has_validation = params.body_model or params.query_model or params.form_model or params.path_params
    has_serialization = params.response_model is not None or params.response_many
    if not has_validation and not has_serialization:
        # Still need to store params for OpenAPI generation
        func._route_params = params
        return func

    @wraps(func)
    def wrapper(*args, **kwargs):
        validate = _should_validate(func, current_app)
        errors = {}

        if validate:
            # Validate path params
            for name, type_ in params.path_params.items():
                if name in kwargs:
                    val, err = validate_path_param(name, kwargs[name], type_)
                    if err:
                        errors.setdefault("path_params", []).append(err)
                    else:
                        kwargs[name] = val

            # Validate query
            if params.query_model:
                q, err = validate_query(params.query_model)
                if err:
                    errors["query_params"] = err
                elif params.query_param_name:
                    kwargs[params.query_param_name] = q

            # Validate body
            if params.body_model:
                b, err = validate_body(params.body_model)
                if err:
                    errors["body_params"] = err
                elif params.body_param_name:
                    kwargs[params.body_param_name] = b

            # Validate form
            if params.form_model:
                f, err = validate_form(params.form_model)
                if err:
                    errors["form_params"] = err
                elif params.form_param_name:
                    kwargs[params.form_param_name] = f

            if errors:
                status_code = current_app.config.get(
                    "FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE", 422
                )
                return make_response(jsonify({"validation_error": errors}), status_code)

        result = current_app.ensure_sync(func)(*args, **kwargs)
        return serialize_response(
            result,
            status_code=params.status_code,
            many=params.response_many,
        )

    wrapper._route_params = params
    wrapper._original_func = func
    return wrapper


class FlaskPydantic:
    """Flask extension for Pydantic-based validation and OpenAPI generation."""

    def __init__(self, app: Flask = None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        app.extensions["flask_pydantic"] = self
        self._wrap_routes(app)

        # Deferred wrapping: re-wrap on first request to catch routes
        # registered after init_app (e.g. blueprints in factory pattern)
        @app.before_request
        def _deferred_wrap():
            self._wrap_routes(app)
            # Remove this handler after first invocation
            app.before_request_funcs[None].remove(_deferred_wrap)

    def _wrap_routes(self, app: Flask):
        """Iterate registered routes and wrap view functions."""
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            view_func = app.view_functions.get(endpoint)
            if view_func is None:
                continue

            # Skip our own doc endpoints
            if endpoint.startswith("flask_pydantic."):
                continue

            wrapped = _wrap_view(view_func, rule, app)
            if wrapped is not view_func:
                app.view_functions[endpoint] = wrapped
```

- [ ] **Step 4: Update `__init__.py` with new public API**

```python
# flask_pydantic/__init__.py
from .docs_decorator import docs  # noqa: F401
from .exceptions import ValidationError  # noqa: F401
from .extension import FlaskPydantic  # noqa: F401
from .markers import Body, Form, Query, Status  # noqa: F401
from .version import __version__  # noqa: F401
```

- [ ] **Step 5: Update version to 2.0.0**

In `flask_pydantic/version.py`, change `__version__` to `"2.0.0"`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_extension.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add flask_pydantic/extension.py flask_pydantic/__init__.py flask_pydantic/version.py tests/test_extension.py
git commit -m "feat: add FlaskPydantic extension with view wrapping and validation"
```

---

### Task 7: OpenAPI Spec Generation

**Files:**
- Create: `flask_pydantic/openapi.py`
- Create: `tests/test_openapi.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_openapi.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_openapi.py -v`
Expected: FAIL

- [ ] **Step 3: Implement OpenAPI spec generation**

This is the largest module. Key responsibilities:
- Iterate `app.url_map` rules and `app.view_functions`
- For each wrapped view, read `_route_params` and `_pydantic_docs`
- For MethodView endpoints, introspect each HTTP method individually
- Generate Pydantic JSON schemas via `model.model_json_schema()` and collect into `components/schemas`
- Use `$ref` references for models
- Convert Werkzeug route syntax (`<int:user_id>`) to OpenAPI syntax (`{user_id}`)
- Auto-add validation error responses for routes with validated params
- Pull descriptions from docstrings, summaries from `@docs()` or first docstring line

Implementation file: `flask_pydantic/openapi.py`

```python
# flask_pydantic/openapi.py
import re
from typing import Any, Dict, List, Optional, Set, Type

from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel

from .inspection import RouteParams, extract_params


def _werkzeug_to_openapi_path(rule_string: str) -> str:
    """Convert '<int:user_id>' to '{user_id}'."""
    return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule_string)


def _collect_schema(
    model: Type[BaseModel], schemas: Dict[str, Any]
) -> Dict[str, str]:
    """Add model schema to components and return a $ref."""
    name = model.__name__
    if name not in schemas:
        json_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        # Extract $defs into top-level schemas
        defs = json_schema.pop("$defs", {})
        schemas[name] = json_schema
        for def_name, def_schema in defs.items():
            if def_name not in schemas:
                schemas[def_name] = def_schema
    return {"$ref": f"#/components/schemas/{name}"}


def _build_operation(
    params: RouteParams,
    docs_meta: dict,
    func: Any,
    schemas: Dict[str, Any],
    validation_error_status: int,
) -> Dict[str, Any]:
    """Build a single OpenAPI operation object."""
    op: Dict[str, Any] = {}

    # Summary and description
    summary = docs_meta.get("summary")
    description = docs_meta.get("description")
    if not description and func.__doc__:
        description = func.__doc__.strip()
    if not summary and description:
        summary = description.split("\n")[0]
    if summary:
        op["summary"] = summary
    if description:
        op["description"] = description

    # Tags — from @docs(tag=...) or blueprint name
    tag = docs_meta.get("tag")
    if not tag:
        tag = docs_meta.get("_blueprint_name")
    if tag:
        op["tags"] = [tag]

    # Operation ID — from @docs(operation_id=...) or auto-generated
    if "operation_id" in docs_meta:
        op["operationId"] = docs_meta["operation_id"]
    elif "_auto_operation_id" in docs_meta:
        op["operationId"] = docs_meta["_auto_operation_id"]

    # Deprecated
    if docs_meta.get("deprecated"):
        op["deprecated"] = True

    # Parameters (path + query)
    parameters: List[Dict] = []
    for name, type_ in params.path_params.items():
        param: Dict[str, Any] = {
            "name": name,
            "in": "path",
            "required": True,
            "schema": _python_type_to_schema(type_),
        }
        parameters.append(param)

    if params.query_model:
        json_schema = params.query_model.model_json_schema()
        properties = json_schema.get("properties", {})
        required_fields = set(json_schema.get("required", []))
        for field_name, field_schema in properties.items():
            param = {
                "name": field_name,
                "in": "query",
                "required": field_name in required_fields,
                "schema": field_schema,
            }
            if "description" in field_schema:
                param["description"] = field_schema["description"]
            parameters.append(param)

    if parameters:
        op["parameters"] = parameters

    # Request body
    if params.body_model:
        ref = _collect_schema(params.body_model, schemas)
        op["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": ref}},
        }
    elif params.form_model:
        ref = _collect_schema(params.form_model, schemas)
        op["requestBody"] = {
            "required": True,
            "content": {"application/x-www-form-urlencoded": {"schema": ref}},
        }

    # Responses
    responses: Dict[str, Any] = {}
    status = str(params.status_code)

    if params.response_model:
        ref = _collect_schema(params.response_model, schemas)
        resp_schema = ref if not params.response_many else {"type": "array", "items": ref}
        responses[status] = {
            "description": "Successful response",
            "content": {"application/json": {"schema": resp_schema}},
        }
    elif params.status_code == 204:
        responses[status] = {"description": "No content"}
    else:
        responses[status] = {"description": "Successful response"}

    # Error responses from @docs() or class errors
    error_models = docs_meta.get("errors", {})
    for err_status, err_model in error_models.items():
        ref = _collect_schema(err_model, schemas)
        responses[str(err_status)] = {
            "description": err_model.__doc__ or f"Error {err_status}",
            "content": {"application/json": {"schema": ref}},
        }

    # Auto-add validation error response
    has_validated = params.body_model or params.query_model or params.form_model or params.path_params
    if has_validated and str(validation_error_status) not in responses:
        responses[str(validation_error_status)] = {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "validation_error": {"type": "object"},
                        },
                    }
                }
            },
        }

    op["responses"] = responses
    return op


def _python_type_to_schema(type_: type) -> dict:
    """Convert a basic Python type to a JSON Schema type."""
    mapping = {
        int: {"type": "integer"},
        float: {"type": "number"},
        str: {"type": "string"},
        bool: {"type": "boolean"},
    }
    return mapping.get(type_, {"type": "string"})


def _get_method_view_class(view_func) -> Optional[type]:
    """If view_func is a MethodView.as_view() result, return the class."""
    view_class = getattr(view_func, "view_class", None)
    if view_class and issubclass(view_class, MethodView):
        return view_class
    # Check wrapped function
    original = getattr(view_func, "_original_func", view_func)
    view_class = getattr(original, "view_class", None)
    if view_class and issubclass(view_class, MethodView):
        return view_class
    return None


def generate_openapi_spec(app: Flask) -> Dict[str, Any]:
    """Generate an OpenAPI 3.1 spec from the Flask app's registered routes."""
    schemas: Dict[str, Any] = {}
    paths: Dict[str, Dict] = {}
    validation_error_status = app.config.get(
        "FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE", 422
    )

    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint.startswith("flask_pydantic.") or endpoint == "static":
            continue

        view_func = app.view_functions.get(endpoint)
        if view_func is None:
            continue

        path = _werkzeug_to_openapi_path(rule.rule)
        if path not in paths:
            paths[path] = {}

        path_param_names = {arg for arg in rule.arguments}
        view_class = _get_method_view_class(view_func)

        # Extract blueprint name from endpoint (e.g. "users.get_user" -> "users")
        blueprint_name = None
        if "." in endpoint:
            blueprint_name = endpoint.rsplit(".", 1)[0]

        if view_class:
            # MethodView: introspect each HTTP method
            class_errors = getattr(view_class, "errors", {})
            methods = {m.lower() for m in rule.methods if m not in ("HEAD", "OPTIONS")}

            for method in methods:
                method_func = getattr(view_class, method, None)
                if method_func is None:
                    continue

                try:
                    method_params = extract_params(method_func, path_param_names)
                except (TypeError, ValueError):
                    continue

                docs_meta = dict(getattr(method_func, "_pydantic_docs", {}))
                # Merge class errors with method errors (method wins on conflict)
                merged_errors = {**class_errors, **docs_meta.get("errors", {})}
                docs_meta["errors"] = merged_errors
                # Auto-tag from blueprint
                if blueprint_name:
                    docs_meta.setdefault("_blueprint_name", blueprint_name)
                # Auto operation ID: ClassName.method
                docs_meta.setdefault("_auto_operation_id", f"{view_class.__name__}.{method}")

                paths[path][method] = _build_operation(
                    method_params, docs_meta, method_func, schemas, validation_error_status
                )
        else:
            # Function-based view
            original = getattr(view_func, "_original_func", view_func)
            route_params = getattr(view_func, "_route_params", None)
            if route_params is None:
                try:
                    route_params = extract_params(original, path_param_names)
                except (TypeError, ValueError):
                    continue

            docs_meta = dict(getattr(original, "_pydantic_docs", {}))
            methods = {m.lower() for m in rule.methods if m not in ("HEAD", "OPTIONS")}
            # Auto-tag from blueprint
            if blueprint_name:
                docs_meta.setdefault("_blueprint_name", blueprint_name)
            # Auto operation ID: blueprint.func_name or just func_name
            func_name = original.__name__
            auto_id = f"{blueprint_name}.{func_name}" if blueprint_name else func_name
            docs_meta.setdefault("_auto_operation_id", auto_id)

            for method in methods:
                paths[path][method] = _build_operation(
                    route_params, docs_meta, original, schemas, validation_error_status
                )

    spec: Dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": app.name,
            "version": "1.0.0",
        },
        "paths": paths,
    }

    if schemas:
        spec["components"] = {"schemas": schemas}

    return spec
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_openapi.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flask_pydantic/openapi.py tests/test_openapi.py
git commit -m "feat: add OpenAPI 3.1 spec generation from route metadata"
```

---

### Task 8: Documentation Endpoints (Swagger UI, ReDoc, JSON, YAML)

**Files:**
- Create: `flask_pydantic/docs_views.py`
- Create: `tests/test_docs_views.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docs_views.py
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
        assert resp.content_type == "application/json"
        data = resp.json
        assert data["openapi"] == "3.1.0"
        assert "/items" in data["paths"]

    def test_yaml_spec_without_pyyaml(self, client, monkeypatch):
        import flask_pydantic.docs_views as dv
        monkeypatch.setattr(dv, "yaml", None)
        resp = client.get("/openapi.yaml")
        assert resp.status_code == 404

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_docs_views.py -v`
Expected: FAIL

- [ ] **Step 3: Implement docs views**

```python
# flask_pydantic/docs_views.py
import json

from flask import Blueprint, current_app, make_response

from .openapi import generate_openapi_spec

try:
    import yaml
except ImportError:
    yaml = None


def create_docs_blueprint(app) -> Blueprint:
    """Create a Blueprint with OpenAPI documentation endpoints."""
    bp = Blueprint("flask_pydantic", __name__)
    _cached_spec = {}

    def _get_spec() -> dict:
        if not _cached_spec:
            _cached_spec["spec"] = generate_openapi_spec(current_app._get_current_object())
        return _cached_spec["spec"]

    # JSON spec
    openapi_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
    if openapi_url:
        @bp.route(openapi_url)
        def openapi_json():
            spec = _get_spec()
            resp = make_response(json.dumps(spec, indent=2))
            resp.mimetype = "application/json"
            return resp

    # YAML spec
    yaml_url = app.config.get("FLASK_PYDANTIC_OPENAPI_YAML_URL", "/openapi.yaml")
    if yaml_url and yaml is not None:
        @bp.route(yaml_url)
        def openapi_yaml():
            spec = _get_spec()
            resp = make_response(yaml.dump(spec, default_flow_style=False, sort_keys=False))
            resp.mimetype = "text/yaml"
            return resp

    # Swagger UI
    docs_url = app.config.get("FLASK_PYDANTIC_DOCS_URL", "/docs")
    cdn_url = app.config.get("FLASK_PYDANTIC_CDN_URL", "https://unpkg.com")
    if docs_url:
        @bp.route(docs_url)
        def swagger_ui():
            spec_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{current_app.name} - Swagger UI</title>
    <link rel="stylesheet" href="{cdn_url}/swagger-ui-dist/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="{cdn_url}/swagger-ui-dist/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({{
            url: "{spec_url}",
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout"
        }});
    </script>
</body>
</html>"""
            return make_response(html)

    # ReDoc
    redoc_url = app.config.get("FLASK_PYDANTIC_REDOC_URL", "/redoc")
    if redoc_url:
        @bp.route(redoc_url)
        def redoc():
            spec_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{current_app.name} - ReDoc</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>body {{ margin: 0; padding: 0; }}</style>
</head>
<body>
    <redoc spec-url="{spec_url}"></redoc>
    <script src="{cdn_url}/redoc/bundles/redoc.standalone.js"></script>
</body>
</html>"""
            return make_response(html)

    return bp
```

- [ ] **Step 4: Register the docs blueprint in the extension**

Update `flask_pydantic/extension.py` — add to `init_app`:

```python
from .docs_views import create_docs_blueprint

def init_app(self, app: Flask):
    app.extensions["flask_pydantic"] = self
    self._wrap_routes(app)
    docs_bp = create_docs_blueprint(app)
    app.register_blueprint(docs_bp)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_docs_views.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add flask_pydantic/docs_views.py flask_pydantic/extension.py tests/test_docs_views.py
git commit -m "feat: add Swagger UI, ReDoc, and OpenAPI JSON/YAML endpoints"
```

---

### Task 9: Update Example App and pyproject.toml

**Files:**
- Modify: `example_app/app.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Rewrite example app to use v2 API**

```python
# example_app/app.py
from typing import Annotated, Optional

from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel, Field

from flask_pydantic import FlaskPydantic, Body, Form, Query, Status, docs

app = Flask("flask_pydantic_app")
app.config["FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE"] = 422


class QueryModel(BaseModel):
    """Query parameters for filtering."""
    age: int = Field(description="Age filter")


class BodyModel(BaseModel):
    """Request body for creating resources."""
    name: str = Field(description="Name of the resource")
    nickname: Optional[str] = Field(None, description="Optional nickname")


class FormModel(BaseModel):
    """Form data for submissions."""
    name: str = Field(description="Name")
    nickname: Optional[str] = Field(None, description="Optional nickname")


class ResponseModel(BaseModel):
    """Standard response."""
    id: int
    age: int
    name: str
    nickname: Optional[str] = None


@app.route("/", methods=["POST"])
@docs(tag="Resources", summary="Create a resource")
def post(
    body: Annotated[BodyModel, Body],
    query: Annotated[QueryModel, Query],
) -> ResponseModel:
    """Basic example with both query and body parameters."""
    return ResponseModel(id=2, age=query.age, name=body.name, nickname=body.nickname)


@app.route("/form", methods=["POST"])
@docs(tag="Resources", summary="Submit a form")
def form_post(
    form: Annotated[FormModel, Form],
    query: Annotated[QueryModel, Query],
) -> ResponseModel:
    """Example with form data and query parameters."""
    return ResponseModel(id=2, age=query.age, name=form.name, nickname=form.nickname)


@app.route("/many", methods=["GET"])
@docs(tag="Resources", summary="Get many resources")
def get_many() -> list[ResponseModel]:
    """Returns multiple serialized objects."""
    return [
        ResponseModel(id=1, age=95, name="Geralt", nickname="White Wolf"),
        ResponseModel(id=2, age=45, name="Triss Merigold", nickname="sorceress"),
    ]


class ResourceDetailView(MethodView):
    """Detail view for a single resource."""
    errors = {404: type("NotFound", (BaseModel,), {"__annotations__": {"detail": str}})}

    def get(self, resource_id: int) -> ResponseModel:
        """Get a resource by ID."""
        return ResponseModel(id=resource_id, age=30, name="Example", nickname=None)

    def delete(self, resource_id: int) -> Annotated[None, Status(204)]:
        """Delete a resource."""
        return None


app.add_url_rule(
    "/resources/<int:resource_id>",
    view_func=ResourceDetailView.as_view("resource_detail"),
)

api = FlaskPydantic(app)
```

- [ ] **Step 2: Update pyproject.toml**

Add optional yaml dependency and bump version:

```toml
[project.optional-dependencies]
yaml = ["PyYAML"]
```

Update version to `"2.0.0"`.

- [ ] **Step 3: Verify example app starts and docs render**

Run: `FLASK_APP=example_app/app.py python -m flask run --port 5001`
Then check: `curl http://localhost:5001/openapi.json | python -m json.tool`
And verify `/docs` and `/redoc` load in a browser.

- [ ] **Step 4: Commit**

```bash
git add example_app/app.py pyproject.toml
git commit -m "feat: update example app and pyproject.toml for v2"
```

---

### Task 10: Remove V1 Code and Legacy Tests

**Files:**
- Delete: `flask_pydantic/core.py`
- Delete: `flask_pydantic/converters.py` (keep if still used by validation.py)
- Delete: `tests/pydantic_v1/` (entire directory)
- Modify: `tests/` — remove tests that only test v1 `@validate` decorator

- [ ] **Step 1: Verify converters.py is still imported**

Check that `flask_pydantic/validation.py` imports `convert_query_params` from `converters.py`. If so, keep `converters.py` but remove pydantic v1 support from it.

- [ ] **Step 2: Remove v1-only files**

```bash
rm flask_pydantic/core.py
rm -rf tests/pydantic_v1/
```

- [ ] **Step 3: Clean up converters.py — remove pydantic v1 code**

Remove the `V1BaseModel` import and the v1 branch in `convert_query_params`.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/pydantic_v1`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove v1 validate decorator and pydantic v1 support"
```

---

### Task 11: Full Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write a comprehensive integration test**

```python
# tests/test_integration.py
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
```

- [ ] **Step 2: Run the full integration test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: all PASS

- [ ] **Step 3: Run entire test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add comprehensive integration tests for v2"
```
