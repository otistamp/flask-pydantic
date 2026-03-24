"""Backwards-compatible @validate decorator for v1 migration."""
from functools import wraps
from typing import Any, Callable, List, Optional, Type

from flask import Response, current_app, jsonify, make_response, request
from pydantic import BaseModel, ValidationError

from .converters import convert_query_params
from .inspection import RouteParams
from .validation import _sanitize_ctx_errors


def _model_dump_json(model: BaseModel, **kwargs):
    return model.model_dump_json(**kwargs)


def _make_json_response(
    content,
    status_code: int,
    by_alias: bool,
    exclude_none: bool = False,
    many: bool = False,
) -> Response:
    if many:
        js = "[{}]".format(
            ", ".join(
                _model_dump_json(m, exclude_none=exclude_none, by_alias=by_alias)
                for m in content
            )
        )
    else:
        js = _model_dump_json(content, exclude_none=exclude_none, by_alias=by_alias)
    response = make_response(js, status_code)
    response.mimetype = "application/json"
    return response


def validate(
    body: Optional[Type[BaseModel]] = None,
    query: Optional[Type[BaseModel]] = None,
    on_success_status: int = 200,
    exclude_none: bool = False,
    response_many: bool = False,
    request_body_many: bool = False,
    response_by_alias: bool = False,
    get_json_params: Optional[dict] = None,
    form: Optional[Type[BaseModel]] = None,
):
    """
    Backwards-compatible @validate decorator.

    Supports both explicit model kwargs and function annotation kwargs.
    Sets request.query_params, request.body_params, request.form_params.
    """

    def decorate(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            q, b, f, err = None, None, None, {}

            # Resolve models: explicit kwargs override, annotations as fallback
            query_in_kwargs = func.__annotations__.get("query")
            query_model = query or query_in_kwargs
            body_in_kwargs = func.__annotations__.get("body")
            body_model = body or body_in_kwargs
            form_in_kwargs = func.__annotations__.get("form")
            form_model = form or form_in_kwargs

            # Validate query
            if query_model:
                query_params = convert_query_params(request.args, query_model)
                try:
                    q = query_model(**query_params)
                except ValidationError as ve:
                    err["query_params"] = _sanitize_ctx_errors(ve.errors())

            # Validate body
            if body_model:
                body_params = request.get_json(**(get_json_params or {}))
                if body_params is None:
                    body_params = {}
                if request_body_many:
                    try:
                        b = [body_model(**item) for item in body_params]
                    except (ValidationError, TypeError) as ve:
                        if isinstance(ve, ValidationError):
                            err["body_params"] = _sanitize_ctx_errors(ve.errors())
                        else:
                            err["body_params"] = [
                                {
                                    "loc": ["root"],
                                    "msg": "is not an array of objects",
                                    "type": "type_error.array",
                                }
                            ]
                else:
                    try:
                        b = body_model(**body_params)
                    except TypeError:
                        content_type = request.headers.get("Content-Type", "").lower()
                        media_type = content_type.split(";")[0]
                        if media_type != "application/json":
                            return make_response(
                                jsonify(
                                    {
                                        "detail": (
                                            f"Unsupported media type '{content_type}' "
                                            "in request. 'application/json' is required."
                                        )
                                    }
                                ),
                                415,
                            )
                        else:
                            return make_response(
                                jsonify({"detail": "Failed to decode JSON body"}), 400
                            )
                    except ValidationError as ve:
                        err["body_params"] = _sanitize_ctx_errors(ve.errors())

            # Validate form
            if form_model:
                try:
                    f = form_model(**request.form)
                except ValidationError as ve:
                    err["form_params"] = _sanitize_ctx_errors(ve.errors())

            # Set on request object
            request.query_params = q
            request.body_params = b
            request.form_params = f

            # Inject kwargs for annotation-style usage
            if query_in_kwargs and q is not None:
                kwargs["query"] = q
            if body_in_kwargs and b is not None:
                kwargs["body"] = b
            if form_in_kwargs and f is not None:
                kwargs["form"] = f

            if err:
                status_code = current_app.config.get(
                    "FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE", 422
                )
                return make_response(
                    jsonify({"validation_error": err}), status_code
                )

            res = current_app.ensure_sync(func)(*args, **kwargs)

            # Serialize response
            if response_many:
                if isinstance(res, (list, tuple)) and all(
                    isinstance(r, BaseModel) for r in res
                ):
                    return _make_json_response(
                        res,
                        on_success_status,
                        by_alias=response_by_alias,
                        exclude_none=exclude_none,
                        many=True,
                    )

            if isinstance(res, BaseModel):
                return _make_json_response(
                    res,
                    on_success_status,
                    exclude_none=exclude_none,
                    by_alias=response_by_alias,
                )

            if (
                isinstance(res, tuple)
                and len(res) in (2, 3)
                and isinstance(res[0], BaseModel)
            ):
                headers = None
                status = on_success_status
                if isinstance(res[1], (dict, tuple, list)):
                    headers = res[1]
                elif len(res) == 3 and isinstance(res[2], (dict, tuple, list)):
                    status = res[1]
                    headers = res[2]
                else:
                    status = res[1]
                ret = _make_json_response(
                    res[0],
                    status,
                    exclude_none=exclude_none,
                    by_alias=response_by_alias,
                )
                if headers:
                    ret.headers.update(headers)
                return ret

            return res

        # Mark as already handled so the extension doesn't re-wrap
        wrapper._route_params = RouteParams(
            body_model=body or func.__annotations__.get("body"),
            query_model=query or func.__annotations__.get("query"),
            form_model=form or func.__annotations__.get("form"),
            response_many=response_many,
            status_code=on_success_status,
        )
        wrapper._validate_compat = True
        wrapper._original_func = func
        return wrapper

    return decorate
