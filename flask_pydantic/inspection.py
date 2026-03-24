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

    return params
