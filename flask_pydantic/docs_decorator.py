from typing import Callable, Dict, Optional, Type

from pydantic import BaseModel


def docs(
    tag: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    operation_id: Optional[str] = None,
    errors: Optional[Dict[int, Type[BaseModel]]] = None,
    validate: Optional[bool] = None,
) -> Callable:
    """Attach OpenAPI metadata to a view function."""
    def decorator(func: Callable) -> Callable:
        meta = {}
        if tag is not None:
            meta["tag"] = tag
        if summary is not None:
            meta["summary"] = summary
        if description is not None:
            meta["description"] = description
        if deprecated:
            meta["deprecated"] = True
        if operation_id is not None:
            meta["operation_id"] = operation_id
        if errors is not None:
            meta["errors"] = errors
        if validate is not None:
            meta["validate"] = validate
        func._pydantic_docs = meta
        return func
    return decorator
