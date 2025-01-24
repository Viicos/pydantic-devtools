from __future__ import annotations

import inspect
import sys
from pdb import Pdb
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group, RenderableType
from rich.markup import escape
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from ._utils import get_field_annotation
from .pretty_print import pps

if TYPE_CHECKING:
    from pydantic import BaseModel
    from pydantic.fields import FieldInfo


_enable_breakpoint = True


def enable_breakpoint() -> None:
    global _enable_breakpoint
    _enable_breakpoint = True


def disable_breakpoint() -> None:
    global _enable_breakpoint
    _enable_breakpoint = False


class PydanticPdb(Pdb):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.default_max_depth: int | None = kwargs.pop("max_depth", None)
        super().__init__(*args, **kwargs)
        self.prompt = "(Pydantic pdb) "
        self._console = Console(file=self.stdout)

    def _msg_schema(self, arg: str, *, max_depth: int | None) -> None:
        try:
            val = self._getval(arg)
        except Exception:
            return  # _getval() has displayed the error

        try:
            pps(val, console=self._console, max_depth=max_depth)
        except Exception:
            self._error_exc()  # pyright: ignore[reportAttributeAccessIssue]

    def do_pps(self, arg: str) -> None:
        """Pretty-print the Pydantic core schema."""

        args = arg.split()
        if not len(args):
            return

        arg, *depth_tp = args

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

    def _gsc_repr_cls(self, cls: type[Any], message: str) -> RenderableType:
        try:
            model_lineno = inspect.getsourcelines(cls)[1]
            model_fn = inspect.getabsfile(cls)
            cls_location = f" ({self.canonic(model_fn)}:L{model_lineno})"
        except (OSError, TypeError):
            cls_location = ""
        return f":red_square: [bold red]{message} '{escape(cls.__name__)}'{cls_location}[/bold red]"

    def _gsc_repr_model(self, cls: type[BaseModel]) -> RenderableType:
        return self._gsc_repr_cls(cls, "Building schema for Model")

    def _gsc_repr_dataclass(self, cls: type[Any]) -> RenderableType:
        # pydantic.dataclasses.is_pydanticdataclass does not work for incomplete dataclasses:
        dc_repr = "Pydantic dataclass" if "__pydantic_fields__" in cls.__dict__ else "dataclass"
        return self._gsc_repr_cls(cls, f"Building schema for {dc_repr}")

    def _gsc_repr_typeddict(self, cls: type[Any]) -> RenderableType:
        return self._gsc_repr_cls(cls, "Building schema for TypedDict")

    def _gsc_repr_namedtuple(self, cls: type[Any]) -> RenderableType:
        return self._gsc_repr_cls(cls, "Building schema for NamedTuple")

    def _gsc_repr_field(self, name: str, field_info: FieldInfo, parent_cls: type[Any]) -> RenderableType:
        annotation = get_field_annotation(parent_cls, name)
        repr_field = f":green_circle: [bold green]Field {name!r}[/bold green]"

        table = Table(show_header=False, pad_edge=False, box=None, expand=True)
        table.add_column("1", ratio=1)
        table.add_column("2", ratio=5)
        table.add_row("FieldInfo annotation", Syntax(f"{field_info.annotation}", lexer="pycon"))

        if annotation is not None:
            table.add_row("Original annotation", Syntax(annotation, lexer="python"))

        return Group(
            repr_field,
            table,
        )

    def do_pc(self, arg: str) -> None:
        """Print context about the current Pydantic schema generation process."""

        from pydantic import BaseModel
        from pydantic._internal._generate_schema import GenerateSchema
        from pydantic._internal._generics import _GENERIC_TYPES_CACHE, _generic_recursion_cache
        from pydantic._internal._model_construction import ModelMetaclass

        generic_recursion_cache = _generic_recursion_cache.get()

        tree = Tree(label="GS tree", hide_root=True)

        node = tree
        current_cls: type[Any] | None = None
        last_gen_schema_inst: GenerateSchema | None = None

        for frame, _ in self.stack:
            gen_schema_inst = frame.f_locals.get("self")
            if isinstance(gen_schema_inst, GenerateSchema):
                last_gen_schema_inst = gen_schema_inst
            method_name = frame.f_code.co_name
            if method_name == "_model_schema":
                model_cls: type[BaseModel] = frame.f_locals["cls"]
                current_cls = model_cls
                node = node.add(self._gsc_repr_model(model_cls))

            if method_name == "_typed_dict_schema":
                td_cls: type[Any] = frame.f_locals["typed_dict_cls"]
                current_cls = td_cls
                node = node.add(self._gsc_repr_typeddict(td_cls))

            if method_name == "_namedtuple_schema":
                nt_cls: type[Any] = frame.f_locals["namedtuple_cls"]
                current_cls = nt_cls
                node = node.add(self._gsc_repr_namedtuple(nt_cls))

            if method_name == "_dataclass_schema":
                dc_cls: type[Any] = frame.f_locals["dataclass"]
                current_cls = dc_cls
                node = node.add(self._gsc_repr_dataclass(dc_cls))

            if method_name == "_common_field_schema":
                field_name: str = frame.f_locals["name"]
                field_info: FieldInfo = frame.f_locals["field_info"]
                assert current_cls is not None
                node.add(self._gsc_repr_field(field_name, field_info, current_cls))

            if (
                method_name == "__new__"
                and inspect.isclass(mcs := frame.f_locals.get("mcs"))
                and issubclass(mcs, ModelMetaclass)
            ):
                cls_name: str = frame.f_locals["cls_name"]
                new_cls: type[BaseModel] | None = frame.f_locals.get("cls")
                if new_cls is not None:
                    node = node.add(self._gsc_repr_cls(new_cls, "Creating Model"))
                else:
                    node = node.add(f":red_square: [bold red]Creating model '{escape(cls_name)}'[/bold red]")

            if method_name == "__class_getitem__" and issubclass(frame.f_locals["cls"], BaseModel):
                model_name: str | None = frame.f_locals.get("model_name")
                cached = " (cached)" if frame.f_locals.get("cached") else ""
                if model_name:
                    node = node.add(
                        f":red_square: [bold red]Parametrizing model '{escape(model_name)}'{cached}[/bold red]"
                    )
                else:
                    origin_cls: type[BaseModel] = frame.f_locals["cls"]
                    typevar_values: tuple[type[Any], ...] = frame.f_locals["typevar_values"]
                    node = node.add(
                        f":red_square: [bold red]Parametrizing model '{escape(origin_cls.__name__)}'{cached} "
                        f"with types: {typevar_values} [/bold red]",
                    )

            if method_name == "model_rebuild" and (
                frame.f_locals["force"] or not frame.f_locals["cls"].__pydantic_complete__
            ):
                rebuilt_cls: type[BaseModel] = frame.f_locals["cls"]
                node = node.add(f":red_square: [bold red]Rebuilding model '{escape(rebuilt_cls.__name__)}'[/bold red]")

        if last_gen_schema_inst is not None:
            model_type_stack = last_gen_schema_inst.model_type_stack._stack
            field_name_stack = last_gen_schema_inst.field_name_stack._stack
            defs = last_gen_schema_inst.defs
            typevars_map = last_gen_schema_inst._typevars_map

            self._console.print(f"[italic]GenerateSchema ID:[/italic] {id(last_gen_schema_inst)}")
            if defs._definitions:  # pyright: ignore[reportAttributeAccessIssue]
                self._console.print(f"[italic]Collected defs:[/italic] {', '.join(defs._definitions.keys())}")  # pyright: ignore[reportAttributeAccessIssue]
            if model_type_stack:
                self._console.print(
                    f"[italic]Model type stack:[/italic] {', '.join(cls.__name__ for cls in model_type_stack)}"
                )
            if field_name_stack:
                self._console.print(f"[italic]Field name stack:[/italic] {', '.join(field_name_stack)}")
            if typevars_map:
                self._console.print("[italic]Typevars map:[/italic]", typevars_map, end=" ")

        if generic_recursion_cache:
            self._console.print("[italic]Generic recursion cache:[/italic]", generic_recursion_cache, end=" ")

        cached_generic_models = [
            (tp.__name__, tp.__pydantic_generic_metadata__)
            for val in _GENERIC_TYPES_CACHE.valuerefs()
            if (tp := val()) is not None
        ]
        if cached_generic_models:
            self._console.print("[italic]Cached generic models:[/italic]", cached_generic_models, end=" ")

        self._console.print(tree)


def pdb(*, max_depth: int | None = None) -> None:
    if _enable_breakpoint:
        pdb = PydanticPdb(max_depth=max_depth)
        pdb.set_trace(sys._getframe().f_back)
