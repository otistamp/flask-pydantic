# Flask-Pydantic v2 Design Spec

## Overview

A clean-break major version of flask-pydantic that replaces the `@validate` decorator with a Flask extension. The extension inspects type hints on route functions and `MethodView` classes to automatically handle request validation, response serialization, and OpenAPI 3.1 spec generation.

## Goals

- Eliminate the `@validate` decorator in favor of standard Python type hints with `Annotated` markers
- Auto-generate OpenAPI 3.1 spec from type hints and Pydantic model metadata
- Serve Swagger UI and ReDoc from CDN at configurable endpoints
- Support both function-based views and Flask's `MethodView`
- Make validation optional (on by default) while always generating the spec

## Non-Goals

- Backwards compatibility with flask-pydantic v1 `@validate` decorator
- Bundling Swagger UI / ReDoc JS assets in the package
- Supporting Pydantic v1 models
- `Header` / `Cookie` parameter markers (may be added in a future minor release)

## Architecture

### Extension Registration

```python
from flask import Flask
from flask_pydantic import FlaskPydantic

app = Flask(__name__)
api = FlaskPydantic(app)

# or factory pattern
api = FlaskPydantic()
api.init_app(app)
```

The extension:
1. During `init_app`, wraps each view function with a validation/serialization layer by iterating `app.url_map` and replacing view functions in `app.view_functions`. For the factory pattern, this wrapping is deferred using `app.before_request` on the first request to ensure all routes (including blueprint routes) are registered before scanning.
2. Registers documentation endpoints (`/openapi.json`, `/openapi.yaml`, `/docs`, `/redoc`)
3. Builds the OpenAPI spec lazily on first request to a docs endpoint, then caches it

### Request Parameter Markers

Explicit `Annotated` markers declare parameter sources:

```python
from typing import Annotated
from flask_pydantic import Body, Query, Form

@app.route("/users/<int:user_id>", methods=["PUT"])
def update_user(
    user_id: int,                            # path param (inferred from route)
    body: Annotated[UpdateUser, Body],       # JSON body
    query: Annotated[FilterParams, Query],   # query string
) -> UserResponse:
    ...
```

**Markers:**
- `Body` — JSON request body. Type must be a Pydantic `BaseModel`. Mutually exclusive with `Form` on the same route.
- `Query` — Query string parameters. Type must be a Pydantic `BaseModel`.
- `Form` — Form-encoded body. Type must be a Pydantic `BaseModel`. Mutually exclusive with `Body` on the same route.
- Path parameters — no marker needed; inferred by matching parameter name to `<param>` segments in the route rule. Type can be any type supported by Pydantic's `TypeAdapter`.

A route with both `Body` and `Form` markers raises a configuration error at startup.

### Response Modeling

The return type annotation declares the success response schema:

```python
@app.route("/users/<int:user_id>")
def get_user(user_id: int) -> UserResponse:
    ...
```

Default status code is 200. Override with `Status`:

```python
from flask_pydantic import Status

@app.route("/users", methods=["POST"])
def create_user(body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
    ...
```

The extension serializes the returned Pydantic model to JSON automatically.

**Return type handling:**
- `BaseModel` — serialized to JSON with the annotated status code
- `list[BaseModel]` — serialized as a JSON array
- `Annotated[None, Status(204)]` — returns empty body with the given status code
- `dict` — passed through to Flask's `jsonify` (no schema in OpenAPI spec)
- `Response` — passed through unchanged (no schema in OpenAPI spec)
- `tuple(model, status)` or `tuple(model, status, headers)` — model is serialized, status/headers applied
- No return annotation — treated as opaque, no OpenAPI response schema generated

### Error Responses

#### Function-based views

Use the `@docs()` decorator:

```python
from flask_pydantic import docs

@app.route("/users/<int:user_id>")
@docs(errors={404: NotFoundError, 422: ValidationError})
def get_user(user_id: int) -> UserResponse:
    ...
```

#### Class-based views (MethodView)

Use a class-level `errors` attribute shared across all methods:

```python
from flask.views import MethodView

class UserView(MethodView):
    errors = {404: NotFoundError, 422: ValidationError}

    def get(self, user_id: int) -> UserResponse:
        ...

    def post(self, body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
        ...
```

#### Auto-documented errors

The extension automatically adds a validation error response to the OpenAPI spec for any route that has validated parameters, even without explicit `errors` declarations. The status code defaults to 422 and is configurable via `FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE`.

**Merging behavior:** Method-level `@docs(errors=...)` on a `MethodView` merges with (and overrides on conflict) the class-level `errors` dict.

### OpenAPI Metadata Sources

Metadata is derived from existing Python/Pydantic/Flask constructs wherever possible:

| OpenAPI field | Source |
|---|---|
| Schema descriptions | Pydantic model docstrings |
| Field descriptions | `Field(description=...)` |
| Field examples | `Field(examples=[...])` |
| Schema examples | `model_config` / `json_schema_extra` |
| Operation description | Function/method docstring |
| Tag | Blueprint name (auto) or `@docs(tag=...)` |
| Summary | First line of docstring (auto) or `@docs(summary=...)` |
| Operation ID | Auto-generated as `blueprint_name.function_name` (or `ClassName.method_name` for MethodView) or `@docs(operation_id=...)` |

#### `@docs()` decorator (optional overrides)

```python
@docs(
    tag="Users",
    summary="Create a new user",
    description="Creates a user account and sends a welcome email.",
    deprecated=True,
    operation_id="createUser",
    errors={404: NotFoundError},
)
```

For `MethodView`, `@docs()` can be applied to individual methods for per-method overrides.

### Documentation Endpoints

Registered automatically by the extension:

| Endpoint | Description |
|---|---|
| `GET /openapi.json` | OpenAPI 3.1 JSON spec |
| `GET /openapi.yaml` | OpenAPI 3.1 YAML spec |
| `GET /docs` | Swagger UI (loaded from CDN) |
| `GET /redoc` | ReDoc (loaded from CDN) |

Configurable via app config:

```python
app.config["FLASK_PYDANTIC_OPENAPI_URL"] = "/openapi.json"       # or None to disable
app.config["FLASK_PYDANTIC_OPENAPI_YAML_URL"] = "/openapi.yaml" # or None to disable
app.config["FLASK_PYDANTIC_DOCS_URL"] = "/docs"                 # or None to disable
app.config["FLASK_PYDANTIC_REDOC_URL"] = "/redoc"               # or None to disable
app.config["FLASK_PYDANTIC_CDN_URL"] = "https://unpkg.com"      # override for corporate environments
app.config["FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE"] = 422 # validation error status code
```

Swagger UI and ReDoc JS/CSS are loaded from unpkg or cdnjs CDN. No assets are bundled.

### Validation Behavior

Validation is enabled by default. It can be disabled globally or per-route:

```python
# Global
app.config["FLASK_PYDANTIC_VALIDATE"] = False

# Per-route
@docs(validate=False)
def get_user(user_id: int) -> UserResponse:
    ...
```

When validation is off, type hints still drive OpenAPI spec generation but no runtime parsing/validation occurs.

When validation is on:
- Invalid requests return a JSON error response (status 422 by default, configurable via `FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE`)
- The error format: `{"validation_error": {"body_params": [...], "query_params": [...]}}`

### Module Structure

```
flask_pydantic/
    __init__.py          # Public API exports (FlaskPydantic, Body, Query, Form, Status, docs)
    extension.py         # FlaskPydantic extension class, init_app, hooks
    markers.py           # Body, Query, Form, Status marker classes
    inspection.py        # Type hint introspection, parameter extraction
    validation.py        # Request parsing and validation logic
    serialization.py     # Response serialization
    openapi.py           # OpenAPI 3.1 spec generation from introspected routes
    docs.py              # Documentation endpoint views (Swagger UI, ReDoc HTML)
    exceptions.py        # Exception classes
    version.py           # Version string
```

### Dependencies

- Flask (existing)
- pydantic >= 2.0 (existing, drop v1 support)
- PyYAML (optional extra: `pip install flask-pydantic[yaml]`; YAML endpoint disabled when absent)

No new heavy dependencies. Swagger UI and ReDoc are CDN-loaded.

## Example: Complete Usage

```python
from typing import Annotated, Optional
from flask import Flask
from flask.views import MethodView
from flask_pydantic import FlaskPydantic, Body, Query, Status, docs
from pydantic import BaseModel, Field

app = Flask(__name__)
api = FlaskPydantic(app)


class UserQuery(BaseModel):
    """Filter parameters for user queries."""
    age_min: Optional[int] = Field(None, description="Minimum age filter")
    age_max: Optional[int] = Field(None, description="Maximum age filter")


class CreateUser(BaseModel):
    """Payload to create a new user."""
    name: str = Field(description="Full name", examples=["Jane Doe"])
    email: str = Field(description="Email address")


class UserResponse(BaseModel):
    """A user resource."""
    id: int
    name: str
    email: str


class NotFoundError(BaseModel):
    """Resource not found."""
    detail: str = Field(examples=["User not found"])


# Function-based view
@app.route("/health")
def health() -> dict:
    return {"status": "ok"}


# Function-based view with docs
@app.route("/users", methods=["POST"])
@docs(tag="Users", summary="Create a user")
def create_user(body: Annotated[CreateUser, Body]) -> Annotated[UserResponse, Status(201)]:
    """Creates a new user account."""
    ...


# Class-based view
class UserDetailView(MethodView):
    errors = {404: NotFoundError}

    def get(self, user_id: int) -> UserResponse:
        """Get a user by ID."""
        ...

    def delete(self, user_id: int) -> Annotated[None, Status(204)]:
        """Delete a user."""
        ...

app.add_url_rule("/users/<int:user_id>", view_func=UserDetailView.as_view("user_detail"))
```
