from __future__ import annotations

import sys
from pdb import Pdb
from typing import Any

from rich.console import Console
from rich.pretty import Pretty

_console = Console()


def _clean_schema(obj: Any) -> Any:
    """A utility function to remove irrelevant information from a core schema.

    The logic mimics the `pydantic._internal._core_utils._strip_metadata` function,
    with some deviations regarding metadata handling.
    """

    if isinstance(obj, dict):
        new_dct = {}
        for k, v in obj.items():
            if k == "metadata":
                new_metadata = {}

                for meta_k, meta_v in v.items():
                    if meta_k in ("pydantic_js_functions", "pydantic_js_annotation_functions"):
                        new_metadata["js_metadata"] = "<stripped>"
                    else:
                        new_metadata[meta_k] = _clean_schema(meta_v)

                if len(new_metadata) == 1:
                    new_metadata = {"<stripped>"}

                new_dct[k] = new_metadata
            # Remove some defaults:
            elif k in ("custom_init", "root_model") and not v:
                continue
            else:
                new_dct[k] = _clean_schema(v)

        return new_dct
    elif isinstance(obj, list):
        return [_clean_schema(v) for v in obj]
    else:
        return obj


class PydanticPdb(Pdb):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.default_max_depth: int | None = kwargs.pop("max_depth", None)
        super().__init__(*args, **kwargs)
        self.prompt = "(Pydantic pdb) "

    def _msg_schema(self, arg: str, *, max_depth: int | None) -> None:
        try:
            val = self._getval(arg)
        except Exception:
            return  # _getval() has displayed the error

        cleaned_schema = _clean_schema(val)
        with _console.capture() as capture:
            _console.print(Pretty(cleaned_schema, max_depth=max_depth))

        try:
            self.message(capture.get())
        except Exception:
            self._error_exc()  # pyright: ignore[reportAttributeAccessIssue]

    def do_pps(self, arg: str) -> None:
        """Pretty-print the Pydantic core schema."""

        arg, *depth_tp = arg.split()

        if depth_tp:
            try:
                max_depth = int(depth_tp[0])
                if max_depth <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Expected a positive integer for depth, got {depth_tp[0]!r}")
        else:
            max_depth = self.default_max_depth

        self._msg_schema(arg, max_depth=max_depth)

    complete_pps = Pdb._complete_expression


def pdb(*, max_depth: int | None = None) -> None:
    pdb = PydanticPdb(max_depth=max_depth)
    pdb.set_trace(sys._getframe().f_back)
