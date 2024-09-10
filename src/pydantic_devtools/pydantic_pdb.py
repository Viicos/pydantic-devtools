from __future__ import annotations

import inspect
import sys
from pdb import Pdb
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group, RenderableType
from rich.markup import escape
from rich.pretty import pprint
from rich.syntax import Syntax
from rich.tree import Tree

from ._utils import clean_schema, get_field_annotation

if TYPE_CHECKING:
    from pydantic import BaseModel


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

        cleaned_schema = clean_schema(val)

        try:
            pprint(cleaned_schema, console=self._console, max_depth=max_depth)
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

    def _gsc_repr_cls(self, cls: type[Any], message: str) -> RenderableType:
        try:
            model_lineno = inspect.getsourcelines(cls)[1]
            model_fn = inspect.getabsfile(cls)
            cls_location = f" ({self.canonic(model_fn)}:L{model_lineno})"
        except (OSError, TypeError):
            cls_location = ""
        return f":red_square: [bold red]{message} '{escape(cls.__name__)}'{cls_location}[/bold red]"

    def _gsc_repr_model(self, model_cls: type[BaseModel]) -> RenderableType:
        return self._gsc_repr_cls(model_cls, "Building schema for Model")

    def _gsc_repr_typeddict(self, model_cls: type[Any]) -> RenderableType:
        return self._gsc_repr_cls(model_cls, "Building schema for TypedDict")

    def _gsc_repr_namedtuple(self, model_cls: type[Any]) -> RenderableType:
        return self._gsc_repr_cls(model_cls, "Building schema for NamedTuple")

    def _gsc_repr_field(self, name: str, parent_cls: type[Any]) -> RenderableType:
        annotation = get_field_annotation(parent_cls, name)
        repr_field = f":green_circle: [bold green]Field {name!r}[/bold green]"
        if annotation is None:
            return repr_field

        return Group(repr_field, Syntax(f"{name}: {annotation}", lexer="python", theme="monokai", line_numbers=False))

    def do_pc(self, arg: str) -> None:
        """Print context about the current Pydantic schema generation process."""

        from pydantic import BaseModel
        from pydantic._internal._generate_schema import GenerateSchema
        from pydantic._internal._generics import _generic_recursion_cache
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

            if method_name == "_common_field_schema":
                field_name: str = frame.f_locals["name"]
                assert current_cls is not None
                node.add(self._gsc_repr_field(field_name, current_cls))

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
                    node = node.add(f":red_square: [bold red] Creating model '{escape(cls_name)}'[/bold red]")

            if method_name == "__class_getitem__" and issubclass(frame.f_locals["cls"], BaseModel):
                model_name: str | None = frame.f_locals["model_name"]
                if model_name:
                    node = node.add(f":red_square: [bold red] Parametrizing model '{escape(model_name)}'[/bold red]")
                else:
                    origin_cls: type[BaseModel] = frame.f_locals["cls"]
                    typevar_values: tuple[type[Any], ...] = frame.f_locals["typevar_values"]
                    node = node.add(
                        f":red_square: [bold red] Parametrizing model '{escape(origin_cls.__name__)}' "
                        f"with types: {typevar_values} [/bold red]",
                    )

        if last_gen_schema_inst is not None:
            model_type_stack = last_gen_schema_inst.model_type_stack._stack
            field_name_stack = last_gen_schema_inst.field_name_stack._stack
            defs = last_gen_schema_inst.defs
            typevars_map = last_gen_schema_inst._typevars_map
            if defs.definitions:
                self._console.print(f"[underline]Collected defs:[/underline] {', '.join(defs.definitions.keys())}")
            if model_type_stack:
                self._console.print(
                    f"[underline]Model type stack:[/underline] {', '.join(cls.__name__ for cls in model_type_stack)}"
                )
            if field_name_stack:
                self._console.print(f"[underline]Field name stack:[/underline] {', '.join(field_name_stack)}")
            if typevars_map:
                self._console.print("[underline]Typevars map:[/underline]", typevars_map, end=" ")

        if generic_recursion_cache:
            self._console.print("[underline]Generic recursion cache:[/underline]", generic_recursion_cache, end=" ")

        self._console.print(tree)


def pdb(*, max_depth: int | None = None) -> None:
    pdb = PydanticPdb(max_depth=max_depth)
    pdb.set_trace(sys._getframe().f_back)
