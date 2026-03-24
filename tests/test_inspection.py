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
