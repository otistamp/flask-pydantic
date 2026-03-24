from functools import wraps
from typing import Any, Callable, Set

from flask import Flask, current_app, jsonify, make_response
from flask.views import MethodView
from pydantic import BaseModel

from .inspection import RouteParams, extract_params
from .serialization import serialize_response
from .validation import validate_body, validate_form, validate_path_param, validate_query


def _get_path_param_names(rule) -> Set[str]:
    return {arg for arg in rule.arguments}


def _get_docs_meta(func: Callable) -> dict:
    return getattr(func, "_pydantic_docs", {})


def _should_validate(func: Callable, app: Flask) -> bool:
    docs_meta = _get_docs_meta(func)
    if "validate" in docs_meta:
        return docs_meta["validate"]
    return app.config.get("FLASK_PYDANTIC_VALIDATE", True)


def _make_method_wrapper(method_func: Callable, params: RouteParams) -> Callable:
    """Create a wrapper for a single HTTP method that validates and serializes."""

    @wraps(method_func)
    def wrapper(*args, **kwargs):
        validate = _should_validate(method_func, current_app)
        errors = {}

        if validate:
            for name, type_ in params.path_params.items():
                if name in kwargs:
                    val, err = validate_path_param(name, kwargs[name], type_)
                    if err:
                        errors.setdefault("path_params", []).append(err)
                    else:
                        kwargs[name] = val

            if params.query_model:
                q, err = validate_query(params.query_model)
                if err:
                    errors["query_params"] = err
                elif params.query_param_name:
                    kwargs[params.query_param_name] = q

            if params.body_model:
                b, err = validate_body(params.body_model)
                if err:
                    errors["body_params"] = err
                elif params.body_param_name:
                    kwargs[params.body_param_name] = b

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

        result = current_app.ensure_sync(method_func)(*args, **kwargs)
        return serialize_response(
            result, status_code=params.status_code, many=params.response_many,
        )

    wrapper._route_params = params
    wrapper._original_func = method_func
    return wrapper


def _wrap_view(func: Callable, rule, app: Flask) -> Callable:
    path_param_names = _get_path_param_names(rule)

    try:
        params = extract_params(func, path_param_names)
    except (TypeError, ValueError, NameError):
        return func

    has_validation = params.body_model or params.query_model or params.form_model or params.path_params
    has_serialization = params.response_model is not None or params.response_many
    if not has_validation and not has_serialization:
        func._route_params = params
        return func

    return _make_method_wrapper(func, params)


def _wrap_method_view(view_func: Callable, rule, app: Flask) -> None:
    """Wrap individual HTTP methods on a MethodView class in-place."""
    view_class = view_func.view_class
    path_param_names = _get_path_param_names(rule)
    http_methods = {m.lower() for m in (view_class.methods or [])}

    for method_name in http_methods:
        method_func = getattr(view_class, method_name, None)
        if method_func is None:
            continue
        # Skip if already wrapped
        if hasattr(method_func, "_route_params"):
            continue

        try:
            params = extract_params(method_func, path_param_names)
        except (TypeError, ValueError, NameError):
            continue

        has_validation = (
            params.body_model or params.query_model or params.form_model or params.path_params
        )
        has_serialization = params.response_model is not None or params.response_many
        if not has_validation and not has_serialization:
            method_func._route_params = params
            continue

        wrapped_method = _make_method_wrapper(method_func, params)
        setattr(view_class, method_name, wrapped_method)

    # Mark the dispatch view_func as handled
    view_func._route_params = True


class FlaskPydantic:
    def __init__(self, app: Flask = None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        from .docs_views import create_docs_blueprint

        app.extensions["flask_pydantic"] = self
        self._wrap_routes(app)
        docs_bp = create_docs_blueprint(app)
        app.register_blueprint(docs_bp)

        # Deferred wrapping for factory pattern
        @app.before_request
        def _deferred_wrap():
            self._wrap_routes(app)
            app.before_request_funcs[None].remove(_deferred_wrap)

    def _wrap_routes(self, app: Flask):
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            view_func = app.view_functions.get(endpoint)
            if view_func is None:
                continue
            if endpoint.startswith("flask_pydantic."):
                continue
            # Skip if already wrapped
            if hasattr(view_func, "_route_params"):
                continue

            # Handle MethodView subclasses
            view_class = getattr(view_func, "view_class", None)
            if view_class is not None and issubclass(view_class, MethodView):
                _wrap_method_view(view_func, rule, app)
                continue

            wrapped = _wrap_view(view_func, rule, app)
            if wrapped is not view_func:
                app.view_functions[endpoint] = wrapped
