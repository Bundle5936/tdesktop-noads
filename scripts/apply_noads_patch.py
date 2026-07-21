#!/usr/bin/env python3
"""Apply (or auto-heal) the no-ads patch onto an extracted/cloned tdesktop tree."""

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
    p.add_argument("--src", required=True, help="tdesktop source root")
    p.add_argument("--patch", required=True, help="path to .patch file")
    p.add_argument("--cli", required=True, help="path to tdesktop_noads.py")
    p.add_argument("--heal-on-fail", action="store_true")
    args = p.parse_args()

    src = Path(args.src).resolve()
    patch = Path(args.patch).resolve()
    cli = Path(args.cli).resolve()
    m = load_cli(cli)

    try:
        m.apply_patch(src, patch, check_only=False)
        print("patch applied cleanly")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"apply failed: {e}")
        if not args.heal_on_fail:
            return 1
        print("auto-heal…")
        m.auto_heal_patch(src, patch)
        m.apply_patch(src, patch, check_only=False)
        print("healed and applied")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
