from typing import Annotated, Optional

from flask import Flask
from flask.views import MethodView
from pydantic import BaseModel, Field

from flask_pydantic import FlaskPydantic, Body, Form, Query, Status, docs

app = Flask("flask_pydantic_app")
app.config["FLASK_PYDANTIC_VALIDATION_ERROR_STATUS_CODE"] = 422


class QueryModel(BaseModel):
    """Query parameters for filtering."""
    age: int = Field(description="Age filter")


class BodyModel(BaseModel):
    """Request body for creating resources."""
    name: str = Field(description="Name of the resource")
    nickname: Optional[str] = Field(None, description="Optional nickname")


class FormModel(BaseModel):
    """Form data for submissions."""
    name: str = Field(description="Name")
    nickname: Optional[str] = Field(None, description="Optional nickname")


class ResponseModel(BaseModel):
    """Standard response."""
    id: int
    age: int
    name: str
    nickname: Optional[str] = None


class NotFoundError(BaseModel):
    """Resource not found."""
    detail: str


@app.route("/", methods=["POST"])
@docs(tag="Resources", summary="Create a resource")
def post(
    body: Annotated[BodyModel, Body],
    query: Annotated[QueryModel, Query],
) -> ResponseModel:
    """Basic example with both query and body parameters."""
    return ResponseModel(id=2, age=query.age, name=body.name, nickname=body.nickname)


@app.route("/form", methods=["POST"])
@docs(tag="Resources", summary="Submit a form")
def form_post(
    form: Annotated[FormModel, Form],
    query: Annotated[QueryModel, Query],
) -> ResponseModel:
    """Example with form data and query parameters."""
    return ResponseModel(id=2, age=query.age, name=form.name, nickname=form.nickname)


@app.route("/many", methods=["GET"])
@docs(tag="Resources", summary="Get many resources")
def get_many() -> list[ResponseModel]:
    """Returns multiple serialized objects."""
    return [
        ResponseModel(id=1, age=95, name="Geralt", nickname="White Wolf"),
        ResponseModel(id=2, age=45, name="Triss Merigold", nickname="sorceress"),
    ]


class ResourceDetailView(MethodView):
    """Detail view for a single resource."""
    errors = {404: NotFoundError}

    def get(self, resource_id: int) -> ResponseModel:
        """Get a resource by ID."""
        return ResponseModel(id=resource_id, age=30, name="Example", nickname=None)

    def delete(self, resource_id: int) -> Annotated[None, Status(204)]:
        """Delete a resource."""
        return None


app.add_url_rule(
    "/resources/<int:resource_id>",
    view_func=ResourceDetailView.as_view("resource_detail"),
)

api = FlaskPydantic(app)
