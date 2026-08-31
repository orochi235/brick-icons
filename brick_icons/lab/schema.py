"""The lab's config schema, read off the CLI's own parser.

Nothing here lists parameters. A flag added to `cli.build_parser` shows up in
the lab with no other change, which is the only way the two stay in step.
"""
from __future__ import annotations

import argparse

from pathlib import Path

from .. import cli
from ..config import load_config

_TYPES = {int: "int", float: "float", str: "str"}


def _type_name(action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "bool"
    return _TYPES.get(action.type, "str")


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def config_schema(root: Path | str = ".") -> list[dict]:
    """One entry per optional flag: key, flag, type, choices, help, nargs, and
    the value the CLI would actually use.

    `default` is argparse's, which is None for nearly every flag -- the real
    value comes from labels.toml through `load_config`. A lab that read only
    argparse would open on `render_px 0` and tell you that was the CLI's
    behaviour, so `effective` carries the resolved one.
    """
    cfg = load_config(root=str(root))
    out = []
    for a in cli.build_parser()._actions:
        if not a.option_strings or a.dest == "help":
            continue
        nargs = a.nargs if isinstance(a.nargs, int) else None
        out.append({
            "key": a.dest,
            "flag": a.option_strings[0],
            "type": _type_name(a),
            "choices": list(a.choices) if a.choices else None,
            "help": a.help or "",
            "nargs": nargs,
            "default": _jsonable(a.default),
            "effective": _jsonable(getattr(cfg, a.dest, None)),
        })
    return out


def to_argv(part: str, config: dict) -> list[str]:
    """`part` plus one flag per set config key, in schema order.

    A None value means "leave it to the config file", so it is omitted rather
    than passed as an empty string. A false switch is likewise absent: argparse
    store_true flags have no negative form.
    """
    fields = {f["key"]: f for f in config_schema()}
    unknown = set(config) - set(fields)
    if unknown:
        raise KeyError(f"not CLI flags: {sorted(unknown)}")
    argv = [part]
    for key, field in fields.items():
        if key not in config:
            continue
        value = config[key]
        if value is None:
            continue
        if field["type"] == "bool":
            if value:
                argv.append(field["flag"])
            continue
        argv.append(field["flag"])
        values = value if isinstance(value, (list, tuple)) else [value]
        argv.extend(str(v) for v in values)
    return argv
