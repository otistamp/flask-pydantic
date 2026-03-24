from typing import List, Optional


class FlaskPydanticError(Exception):
    """Base exception for flask-pydantic."""
    pass


class ValidationError(FlaskPydanticError):
    """Raised when request validation fails (if configured to raise)."""

    def __init__(
        self,
        body_params: Optional[List[dict]] = None,
        form_params: Optional[List[dict]] = None,
        path_params: Optional[List[dict]] = None,
        query_params: Optional[List[dict]] = None,
    ):
        super().__init__()
        self.body_params = body_params
        self.form_params = form_params
        self.path_params = path_params
        self.query_params = query_params
