from flask_pydantic.docs_decorator import docs
from pydantic import BaseModel


class NotFoundError(BaseModel):
    detail: str


def test_docs_stores_metadata():
    @docs(tag="Users", summary="Get user", description="Gets a user by ID")
    def get_user():
        ...
    meta = get_user._pydantic_docs
    assert meta["tag"] == "Users"
    assert meta["summary"] == "Get user"
    assert meta["description"] == "Gets a user by ID"


def test_docs_stores_errors():
    @docs(errors={404: NotFoundError})
    def get_user():
        ...
    assert get_user._pydantic_docs["errors"] == {404: NotFoundError}


def test_docs_deprecated():
    @docs(deprecated=True)
    def old_endpoint():
        ...
    assert old_endpoint._pydantic_docs["deprecated"] is True


def test_docs_operation_id():
    @docs(operation_id="getUser")
    def get_user():
        ...
    assert get_user._pydantic_docs["operation_id"] == "getUser"


def test_docs_validate_false():
    @docs(validate=False)
    def get_user():
        ...
    assert get_user._pydantic_docs["validate"] is False


def test_no_docs_has_no_attribute():
    def plain():
        ...
    assert not hasattr(plain, "_pydantic_docs")
