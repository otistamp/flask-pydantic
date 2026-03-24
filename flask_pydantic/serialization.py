from typing import Any

from flask import Response, jsonify, make_response
from pydantic import BaseModel


def serialize_response(result: Any, status_code: int, many: bool = False) -> Response:
    """Serialize a view function's return value into a Flask Response."""
    if isinstance(result, Response):
        return result

    if result is None:
        return make_response("", status_code)

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

    if many and isinstance(result, list):
        js = "[" + ", ".join(m.model_dump_json() for m in result) + "]"
        response = make_response(js, status_code)
        response.mimetype = "application/json"
        return response

    if isinstance(result, BaseModel):
        response = make_response(result.model_dump_json(), status_code)
        response.mimetype = "application/json"
        return response

    if isinstance(result, dict):
        return make_response(jsonify(result), status_code)

    return make_response(result, status_code)
