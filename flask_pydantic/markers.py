class _Marker:
    """Base sentinel for Annotated parameter markers."""
    pass


class Body(_Marker):
    """Marks a parameter as JSON request body."""
    pass


class Query(_Marker):
    """Marks a parameter as query string parameters."""
    pass


class Form(_Marker):
    """Marks a parameter as form-encoded body."""
    pass


class Status:
    """Annotates a return type with an HTTP status code."""
    __slots__ = ("code",)

    def __init__(self, code: int = 200):
        self.code = code
