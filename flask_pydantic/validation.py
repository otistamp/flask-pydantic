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
    query_params = convert_query_params(request.args, model)
    try:
        return model(**query_params), None
    except ValidationError as e:
        return None, _sanitize_ctx_errors(e.errors())


def validate_form(
    model: Type[BaseModel],
) -> Tuple[Optional[BaseModel], Optional[List[dict]]]:
    try:
        return model(**request.form), None
    except ValidationError as e:
        return None, _sanitize_ctx_errors(e.errors())


def validate_path_param(
    name: str, value: Any, type_: type
) -> Tuple[Optional[Any], Optional[dict]]:
    try:
        adapter = TypeAdapter(type_)
        return adapter.validate_python(value), None
    except ValidationError as e:
        err = e.errors()[0]
        err["loc"] = [name]
        return None, err
