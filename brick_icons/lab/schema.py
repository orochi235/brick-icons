"""The lab's config schema, read off the CLI's own parser.

Nothing here lists parameters. A flag added to `cli.build_parser` shows up in
the lab with no other change, which is the only way the two stay in step.
"""
from __future__ import annotations

import argparse

from .. import cli

_TYPES = {int: "int", float: "float", str: "str"}


def _type_name(action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "bool"
    return _TYPES.get(action.type, "str")


def config_schema() -> list[dict]:
    """One entry per optional flag: key, flag, type, choices, help, nargs."""
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
            "default": a.default,
        })
    return out
