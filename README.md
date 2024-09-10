# pydantic-devtools

A collection of utilities to facilitate debugging of Pydantic's internals.

## The Pydantic debugger

`pydantic-devtools` provides a custom [`Pdb`](https://docs.python.org/3/library/pdb.html#pdb.Pdb)
class, adding various commands.`pps` (pretty-print schema) command to debug Pydantic core schemas.

To use the Pydantic debugger:
- set the [`PYTHONBREAKPOINT`](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONBREAKPOINT)
  environment variable to `pydantic_devtools.pdb`.
- In your code, add a `breakpoint()` call. The Pydantic debugger will be used.

### `pps` command

The `pps` (pretty-print schema) command can be used to debug Pydantic core schemas:

```shell
(Pydantic pdb) pps schema
{
    'type': 'model-field',
    'schema': {'type': 'definition-ref', 'schema_ref': '...'},
    'metadata': {'<stripped>'}
}
```

By default, generic metadata (related to JSON Schema generation) is stripped.

Optionally, a `max_depth` argument can be provided (`pps <schema> <depth>`).
A default value can also be specified as a keyword argument to [`breakpoint()`](https://docs.python.org/3/library/functions.html#breakpoint).

### `pc` command

The `pc` (Pydantic context) command can be used to get information related to the current
schema generation process:

![`pc` command example](assets/pc_example.png "`pc` command example")
