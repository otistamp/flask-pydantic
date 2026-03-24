"""OpenAPI 3.1 spec generation from Flask route metadata."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set, Type

from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel

from .inspection import RouteParams, extract_params


# Werkzeug converter types to OpenAPI schema types
_WERKZEUG_TYPE_MAP = {
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "string": {"type": "string"},
    "path": {"type": "string"},
    "uuid": {"type": "string", "format": "uuid"},
    "any": {"type": "string"},
}

# Python built-in types to JSON Schema types
_PYTHON_TYPE_MAP = {
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
    bool: {"type": "boolean"},
}

# Pattern to match Werkzeug route converters: <converter:name> or <name>
_WERKZEUG_PARAM_RE = re.compile(r"<(?:(\w+):)?(\w+)>")


def _werkzeug_to_openapi_path(rule_string: str) -> str:
    """Convert Werkzeug route syntax ``<int:user_id>`` to OpenAPI ``{user_id}``."""
    return _WERKZEUG_PARAM_RE.sub(r"{\2}", rule_string)


def _python_type_to_schema(type_: type) -> dict:
    """Map a Python built-in type to a JSON Schema snippet."""
    return _PYTHON_TYPE_MAP.get(type_, {"type": "string"})


def _collect_schema(model: Type[BaseModel], schemas: Dict[str, Any]) -> dict:
    """Add a Pydantic model's JSON schema to the components/schemas dict and return a $ref."""
    name = model.__name__
    if name not in schemas:
        json_schema = model.model_json_schema()
        # If the schema has $defs, hoist them into the shared schemas dict
        defs = json_schema.pop("$defs", {})
        for def_name, def_schema in defs.items():
            if def_name not in schemas:
                schemas[def_name] = def_schema
        schemas[name] = json_schema
    return {"$ref": f"#/components/schemas/{name}"}


def _get_method_view_class(view_func):
    """Return the MethodView class from a view function, or None."""
    cls = getattr(view_func, "view_class", None)
    if cls is not None and issubclass(cls, MethodView):
        return cls
    original = getattr(view_func, "_original_func", None)
    if original is not None:
        cls = getattr(original, "view_class", None)
        if cls is not None and issubclass(cls, MethodView):
            return cls
    return None


def _build_operation(
    params: RouteParams,
    docs_meta: dict,
    func,
    schemas: Dict[str, Any],
    validation_error_status: int,
    rule=None,
) -> dict:
    """Build a single OpenAPI operation object from route metadata."""
    operation: Dict[str, Any] = {}

    # Operation ID
    op_id = docs_meta.get("operation_id")
    if op_id:
        operation["operationId"] = op_id
    elif func is not None and hasattr(func, "__name__"):
        operation["operationId"] = func.__name__

    # Tags
    tag = docs_meta.get("tag")
    if tag:
        operation["tags"] = [tag]

    # Summary and description
    summary = docs_meta.get("summary")
    if summary:
        operation["summary"] = summary

    description = docs_meta.get("description")
    if not description and func is not None:
        docstring = getattr(func, "__doc__", None)
        if docstring:
            description = docstring.strip()
    if description:
        operation["description"] = description

    # If no explicit summary but we have a docstring, use first line as summary
    if not summary and func is not None:
        docstring = getattr(func, "__doc__", None)
        if docstring:
            first_line = docstring.strip().split("\n")[0].strip()
            if first_line:
                operation["summary"] = first_line

    if docs_meta.get("deprecated"):
        operation["deprecated"] = True

    # Parameters: path params + query params
    parameters = []

    # Path parameters from route params
    if params.path_params:
        for name, type_ in params.path_params.items():
            param = {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _python_type_to_schema(type_),
            }
            parameters.append(param)
    elif rule is not None:
        # Extract path params from the rule even if not in route_params
        for match in _WERKZEUG_PARAM_RE.finditer(rule.rule):
            converter = match.group(1) or "string"
            name = match.group(2)
            param = {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _WERKZEUG_TYPE_MAP.get(converter, {"type": "string"}),
            }
            parameters.append(param)

    # Query parameters from query model
    if params.query_model:
        query_schema = params.query_model.model_json_schema()
        properties = query_schema.get("properties", {})
        required_fields = set(query_schema.get("required", []))
        for field_name, field_schema in properties.items():
            param = {
                "name": field_name,
                "in": "query",
                "schema": field_schema,
            }
            if field_name in required_fields:
                param["required"] = True
            if "description" in field_schema:
                param["description"] = field_schema["description"]
            parameters.append(param)

    if parameters:
        operation["parameters"] = parameters

    # Request body
    if params.body_model:
        ref = _collect_schema(params.body_model, schemas)
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": ref,
                }
            },
        }
    elif params.form_model:
        ref = _collect_schema(params.form_model, schemas)
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": ref,
                }
            },
        }

    # Responses
    responses: Dict[str, Any] = {}

    status = str(params.status_code)
    if params.response_model:
        ref = _collect_schema(params.response_model, schemas)
        if params.response_many:
            resp_schema = {"type": "array", "items": ref}
        else:
            resp_schema = ref

        resp_desc = params.response_model.__doc__ or "Successful response"
        responses[status] = {
            "description": resp_desc.strip(),
            "content": {
                "application/json": {
                    "schema": resp_schema,
                }
            },
        }
    else:
        # No response model (e.g. 204 No Content)
        responses[status] = {"description": "Successful response"}

    # Error responses from @docs(errors=...)
    errors = docs_meta.get("errors", {})
    for err_status, err_model in errors.items():
        ref = _collect_schema(err_model, schemas)
        err_desc = err_model.__doc__ or "Error response"
        responses[str(err_status)] = {
            "description": err_desc.strip(),
            "content": {
                "application/json": {
                    "schema": ref,
                }
            },
        }

    # Auto-add validation error response if the route has validated params
    has_validation = (
        params.body_model or params.query_model or params.form_model or params.path_params
    )
    if has_validation:
        vs = str(validation_error_status)
        if vs not in responses:
            responses[vs] = {
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

    operation["responses"] = responses
    return operation


def generate_openapi_spec(app: Flask) -> dict:
    """Generate an OpenAPI 3.1 spec from Flask route metadata.

    Must be called within an application context.
    """
    validation_error_status = app.config.get(
        "FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE", 422
    )

    info = {
        "title": app.name or "API",
        "version": app.config.get("API_VERSION", "0.1.0"),
    }
    api_description = app.config.get("API_DESCRIPTION")
    if api_description:
        info["description"] = api_description

    paths: Dict[str, Dict[str, Any]] = {}
    schemas: Dict[str, Any] = {}

    # Ignored endpoints (Flask built-ins)
    ignored_endpoints = {"static"}

    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint in ignored_endpoints:
            continue

        view_func = app.view_functions.get(endpoint)
        if view_func is None:
            continue

        openapi_path = _werkzeug_to_openapi_path(rule.rule)

        # Determine HTTP methods (exclude HEAD/OPTIONS which Flask adds automatically)
        methods = {m.lower() for m in rule.methods} - {"head", "options"}

        # Check if this is a MethodView
        view_class = _get_method_view_class(view_func)

        if view_class is not None:
            # MethodView: introspect each HTTP method on the class
            class_errors = getattr(view_class, "errors", {}) or {}
            path_param_names = {arg for arg in rule.arguments}

            for method_name in methods:
                method_func = getattr(view_class, method_name, None)
                if method_func is None:
                    continue

                # Get route_params: either from the wrapped method or extract fresh
                route_params = getattr(method_func, "_route_params", None)
                if route_params is None or route_params is True:
                    try:
                        route_params = extract_params(method_func, path_param_names)
                    except (TypeError, ValueError, NameError):
                        route_params = RouteParams()

                # Get original function for docstring access
                original_func = getattr(method_func, "_original_func", method_func)

                # Merge docs metadata: class-level errors + method-level @docs
                docs_meta = dict(getattr(original_func, "_pydantic_docs", {}))
                method_errors = dict(class_errors)
                method_errors.update(docs_meta.get("errors", {}))
                if method_errors:
                    docs_meta["errors"] = method_errors

                op = _build_operation(
                    route_params, docs_meta, original_func, schemas,
                    validation_error_status, rule=rule,
                )
                paths.setdefault(openapi_path, {})[method_name] = op
        else:
            # Regular function view
            route_params = getattr(view_func, "_route_params", None)
            if route_params is None:
                path_param_names = {arg for arg in rule.arguments}
                try:
                    route_params = extract_params(view_func, path_param_names)
                except (TypeError, ValueError, NameError):
                    route_params = RouteParams()

            # Get original function for docstring/docs_meta access
            original_func = getattr(view_func, "_original_func", view_func)
            docs_meta = getattr(original_func, "_pydantic_docs", {})

            for method_name in methods:
                op = _build_operation(
                    route_params, docs_meta, original_func, schemas,
                    validation_error_status, rule=rule,
                )
                paths.setdefault(openapi_path, {})[method_name] = op

    spec: Dict[str, Any] = {
        "openapi": "3.1.0",
        "info": info,
        "paths": paths,
    }

    if schemas:
        spec["components"] = {"schemas": schemas}

    return spec
