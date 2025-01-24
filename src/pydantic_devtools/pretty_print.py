from __future__ import annotations

import inspect
from typing import Any

from rich.console import Console
from rich.pretty import pprint

from ._utils import clean_schema


def pps(val: Any, console: Console | None = None, max_depth: int | None = None, strip_metadata: bool = True) -> None:
    from pydantic import BaseModel, TypeAdapter
    from pydantic.dataclasses import is_pydantic_dataclass

    if (inspect.isclass(val) and issubclass(val, BaseModel)) or is_pydantic_dataclass(val):
        val = val.__pydantic_core_schema__
    if isinstance(val, TypeAdapter):
        val = val.core_schema
    cleaned_schema = clean_schema(val, strip_metadata=strip_metadata)

    pprint(cleaned_schema, console=console, max_depth=max_depth)
