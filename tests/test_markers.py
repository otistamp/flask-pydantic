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
