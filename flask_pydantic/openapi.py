import re
from typing import Any, Optional, Type

from flask import Flask
from pydantic import BaseModel

# Flask URL converter → OpenAPI type mapping
CONVERTER_TYPE_MAP = {
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "uuid": {"type": "string", "format": "uuid"},
    "string": {"type": "string"},
    "path": {"type": "string"},
    "default": {"type": "string"},
}


def _flask_path_to_openapi(path: str) -> str:
    """Convert Flask URL path to OpenAPI format.

    /users/<int:user_id> → /users/{user_id}
    /users/<username> → /users/{username}
    """
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", path)


def _get_api_metadata(view_func):
    """Get _api_metadata from a view function, traversing __wrapped__ chain."""
    func = view_func
    while func is not None:
        if hasattr(func, "_api_metadata"):
            return func._api_metadata
        func = getattr(func, "__wrapped__", None)
    return None


def _is_v2_model(model: Any) -> bool:
    """Check if a model is a pydantic v2 BaseModel (not v1)."""
    if model is None:
        return False
    try:
        from pydantic.v1 import BaseModel as V1BaseModel

        if isinstance(model, type) and issubclass(model, V1BaseModel):
            return False
    except ImportError:
        pass
    return isinstance(model, type) and issubclass(model, BaseModel)


def _get_path_params(rule) -> list:
    """Extract path parameters from a Flask URL rule by parsing the rule string."""
    params = []
    for match in re.finditer(r"<(?:(\w+):)?(\w+)>", rule.rule):
        converter_type = match.group(1) or "default"
        arg_name = match.group(2)
        schema = CONVERTER_TYPE_MAP.get(
            converter_type, CONVERTER_TYPE_MAP["default"]
        ).copy()
        params.append(
            {
                "name": arg_name,
                "in": "path",
                "required": True,
                "schema": schema,
            }
        )
    return params


def _get_query_params(model: Type[BaseModel]) -> list:
    """Convert a pydantic query model to OpenAPI query parameters."""
    if not _is_v2_model(model):
        return []
    schema = model.model_json_schema()
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    params = []
    for field_name, field_schema in properties.items():
        param = {
            "name": field_name,
            "in": "query",
            "required": field_name in required,
            "schema": field_schema,
        }
        if "description" in field_schema:
            param["description"] = field_schema["description"]
        params.append(param)
    return params


def _get_request_body(model: Type[BaseModel], many: bool = False) -> Optional[dict]:
    """Build OpenAPI requestBody from a pydantic model."""
    if not _is_v2_model(model):
        return None
    schema = model.model_json_schema()
    if many:
        schema = {"type": "array", "items": schema}
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": schema,
            }
        },
    }


def _get_form_body(model: Type[BaseModel]) -> Optional[dict]:
    """Build OpenAPI requestBody for form data from a pydantic model."""
    if not _is_v2_model(model):
        return None
    schema = model.model_json_schema()
    return {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": schema,
            }
        },
    }


def _get_responses(metadata: dict) -> dict:
    """Build OpenAPI responses from metadata."""
    responses = {}

    # Success response
    status = str(metadata["on_success_status"])
    response_model = metadata.get("response_model")
    if response_model and _is_v2_model(response_model):
        schema = response_model.model_json_schema()
        if metadata.get("response_many"):
            schema = {"type": "array", "items": schema}
        responses[status] = {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": schema,
                }
            },
        }
    else:
        responses[status] = {"description": "Successful response"}

    # Validation error response (when validate=True)
    validate_flag = metadata.get("validate", True)
    if validate_flag:
        responses["400"] = {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "validation_error": {
                                "type": "object",
                            }
                        },
                    }
                }
            },
        }

    # Error responses
    errors = metadata.get("errors")
    if errors:
        for error_status, error_model in errors.items():
            if _is_v2_model(error_model):
                responses[str(error_status)] = {
                    "description": error_model.__doc__ or f"Error {error_status}",
                    "content": {
                        "application/json": {
                            "schema": error_model.model_json_schema(),
                        }
                    },
                }
            else:
                responses[str(error_status)] = {
                    "description": f"Error {error_status}",
                }

    return responses


def _get_docstring_parts(func) -> tuple:
    """Extract summary and description from a function's docstring."""
    doc = func.__doc__
    if not doc:
        return None, None
    lines = doc.strip().splitlines()
    summary = lines[0].strip()
    description = None
    if len(lines) > 1:
        remaining = "\n".join(lines[1:]).strip()
        if remaining:
            description = remaining
    return summary, description


def generate_openapi_spec(
    app: Flask,
    title: Optional[str] = None,
    version: str = "1.0.0",
    description: Optional[str] = None,
) -> dict:
    """Generate an OpenAPI 3.1 spec dict from a Flask app's decorated routes."""
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": title or app.name,
            "version": version,
        },
        "paths": {},
    }
    if description:
        spec["info"]["description"] = description

    # Methods to exclude (Flask internal)
    skip_methods = {"HEAD", "OPTIONS"}

    for rule in app.url_map.iter_rules():
        # Skip static endpoint
        if rule.endpoint == "static":
            continue

        view_func = app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue

        metadata = _get_api_metadata(view_func)
        if metadata is None:
            continue

        openapi_path = _flask_path_to_openapi(rule.rule)

        if openapi_path not in spec["paths"]:
            spec["paths"][openapi_path] = {}

        methods = sorted(rule.methods - skip_methods)
        for method in methods:
            operation = {}

            # operationId from endpoint name
            operation["operationId"] = rule.endpoint
            if len(methods) > 1:
                operation["operationId"] = f"{rule.endpoint}_{method.lower()}"

            # Summary and description from docstring
            original_func = getattr(view_func, "__wrapped__", view_func)
            summary, desc = _get_docstring_parts(original_func)
            if summary:
                operation["summary"] = summary
            if desc:
                operation["description"] = desc

            # Tags from blueprint
            if "." in rule.endpoint:
                blueprint_name = rule.endpoint.rsplit(".", 1)[0]
                operation["tags"] = [blueprint_name]

            # Parameters (path + query)
            params = _get_path_params(rule)
            query_model = metadata.get("query_model")
            if query_model:
                params.extend(_get_query_params(query_model))
            if params:
                operation["parameters"] = params

            # Request body
            body_model = metadata.get("body_model")
            form_model = metadata.get("form_model")
            if body_model:
                req_body = _get_request_body(
                    body_model, many=metadata.get("request_body_many", False)
                )
                if req_body:
                    operation["requestBody"] = req_body
            elif form_model:
                req_body = _get_form_body(form_model)
                if req_body:
                    operation["requestBody"] = req_body

            # Responses
            operation["responses"] = _get_responses(metadata)

            spec["paths"][openapi_path][method.lower()] = operation

    return spec
