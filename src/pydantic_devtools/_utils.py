from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping, Sequence
from typing import Any


def clean_schema(obj: Any, strip_metadata: bool = True) -> Any:
    """A utility function to remove irrelevant information from a core schema."""

    if isinstance(obj, Mapping):
        new_dct = {}
        for k, v in obj.items():
            if k == "metadata" and strip_metadata:
                new_metadata = {}

                for meta_k, meta_v in v.items():
                    if meta_k in ("pydantic_js_functions", "pydantic_js_annotation_functions"):
                        new_metadata["js_metadata"] = "<stripped>"
                    else:
                        new_metadata[meta_k] = clean_schema(meta_v, strip_metadata=strip_metadata)

                if list(new_metadata.keys()) == ["js_metadata"]:
                    new_metadata = {"<stripped>"}

                new_dct[k] = new_metadata
            # Remove some defaults:
            elif k in ("custom_init", "root_model") and not v:
                continue
            else:
                new_dct[k] = clean_schema(v, strip_metadata=strip_metadata)

        return new_dct
    elif isinstance(obj, Sequence) and not isinstance(obj, str):
        return [clean_schema(v, strip_metadata=strip_metadata) for v in obj]
    else:
        return obj


def get_field_annotation(cls: type[Any], field_name: str) -> str | None:
    from pydantic._internal._docs_extraction import _dedent_source_lines

    try:
        model_source = inspect.getsourcelines(cls)[0]
        dedent_source = _dedent_source_lines(model_source)
        model_ast = ast.parse(dedent_source)
    except (OSError, TypeError, SyntaxError):
        return

    stmt = model_ast.body[0]
    if isinstance(stmt, ast.FunctionDef) and stmt.name == "dedent_workaround":
        # `_dedent_source_lines` wrapped the class around the workaround function
        stmt = stmt.body[0]

    assert isinstance(stmt, ast.ClassDef)
    for body_stmt in stmt.body:
        if (
            isinstance(body_stmt, ast.AnnAssign)
            and isinstance(body_stmt.target, ast.Name)
            and body_stmt.target.id == field_name
        ):
            return ast.unparse(body_stmt.annotation)
