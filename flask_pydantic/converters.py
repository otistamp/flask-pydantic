import types
from collections import deque
from typing import Deque, FrozenSet, List, Sequence, Set, Tuple, Type, Union

try:
    from typing import get_args, get_origin
except ImportError:
    from typing_extensions import get_args, get_origin

from pydantic import BaseModel
from werkzeug.datastructures import ImmutableMultiDict

UnionType = getattr(types, "UnionType", Union)

sequence_types = {
    Sequence, List, list, Tuple, tuple, Set, set, FrozenSet, frozenset, Deque, deque,
}


def _is_sequence(type_: Type) -> bool:
    origin = get_origin(type_) or type_
    if origin is Union or origin is UnionType:
        return any(_is_sequence(t) for t in get_args(type_))
    return origin in sequence_types and origin not in (str, bytes)


def convert_query_params(
    query_params: ImmutableMultiDict, model: Type[BaseModel]
) -> dict:
    return {
        **query_params.to_dict(),
        **{
            key: value
            for key, value in query_params.to_dict(flat=False).items()
            if key in model.model_fields
            and _is_sequence(model.model_fields[key].annotation)
        },
    }
