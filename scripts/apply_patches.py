#!/usr/bin/env python3
"""Apply all patches under patches/ (or explicit list) onto a tdesktop tree."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_cli(cli_path: Path):
    spec = importlib.util.spec_from_file_location("tdesktop_noads", cli_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {cli_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--patches-dir", default=None, help="directory of *.patch (sorted)")
    p.add_argument("--patch", action="append", default=[], help="explicit patch path (repeatable)")
    p.add_argument("--cli", required=True)
    p.add_argument("--heal-on-fail", action="store_true")
    args = p.parse_args()

    src = Path(args.src).resolve()
    m = load_cli(Path(args.cli).resolve())

    patches: list[Path] = []
    if args.patch:
        patches = [Path(x).resolve() for x in args.patch]
    elif args.patches_dir:
        d = Path(args.patches_dir).resolve()
        patches = sorted(d.glob("*.patch"))
    else:
        raise SystemExit("need --patches-dir or --patch")

    if not patches:
        raise SystemExit("no patches found")

    for patch in patches:
        print(f"==> {patch.name}")
        try:
            m.apply_patch(src, patch, check_only=False)
            print(f"applied: {patch.name}")
        except Exception as e:  # noqa: BLE001
            print(f"apply failed ({patch.name}): {e}")
            if not args.heal_on_fail:
                return 1
            print(f"auto-heal: {patch.name}")
            m.auto_heal_named_patch(src, patch)
            m.apply_patch(src, patch, check_only=False)
            print(f"healed+applied: {patch.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
