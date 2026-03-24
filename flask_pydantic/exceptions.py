from typing import Dict, List, Optional


class FlaskPydanticError(Exception):
    """Base exception for flask-pydantic."""
    pass


# Legacy alias for backward compatibility
BaseFlaskPydanticException = FlaskPydanticError


class InvalidIterableOfModelsException(FlaskPydanticError):
    """Raised when serialization of response with response_many=True fails."""
    pass


class JsonBodyParsingError(FlaskPydanticError):
    """Exception for errors occurring during parsing of request body."""
    pass


class ManyModelValidationError(FlaskPydanticError):
    """Raised when validation of many models in an iterable fails."""

    def __init__(self, errors: List[dict], *args):
        self._errors = errors
        super().__init__(*args)

    def errors(self):
        return self._errors


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
