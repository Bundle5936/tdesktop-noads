#!/usr/bin/env python3
"""tdesktop-noads — pure-GitHub auto-follow for official Telegram Desktop + no-ads patch.

Designed to run in GitHub Actions with zero local participation:
  follow --auto-heal  → check upstream, apply or regenerate patch, update pin
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATCH = REPO_ROOT / "patches" / "0001-no-sponsored-messages.patch"
DEFAULT_WORK = REPO_ROOT / "work"
DEFAULT_PIN = REPO_ROOT / "versions" / "current.json"
UPSTREAM = "telegramdesktop/tdesktop"
SPONSORED_REL = Path("Telegram/SourceFiles/data/components/sponsored_messages.cpp")
USER_AGENT = "tdesktop-noads-cli/0.3 (+https://github.com/vcshixin/tdesktop-noads)"


class CliError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[tdesktop-noads] {msg}", flush=True)


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


def http_json(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {e.code} for {url}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise CliError(f"Network error for {url}: {e}") from e


def http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    log(f"download {url}")
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_tag(tag: str | None) -> str:
    if not tag:
        data = http_json(f"https://api.github.com/repos/{UPSTREAM}/releases/latest")
        assert isinstance(data, dict)
        tag = data["tag_name"]
        log(f"latest release: {tag}")
    tag = str(tag)
    if not tag.startswith("v"):
        tag = "v" + tag
    return tag


def version_from_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def source_urls(tag: str) -> list[str]:
    ver = version_from_tag(tag)
    return [
        f"https://github.com/{UPSTREAM}/releases/download/{tag}/tdesktop-{ver}-full.tar.gz",
        f"https://github.com/{UPSTREAM}/archive/refs/tags/{tag}.tar.gz",
    ]


def find_source_root(extract_dir: Path) -> Path:
    candidates = sorted(p for p in extract_dir.iterdir() if p.is_dir())
    if not candidates:
        raise CliError(f"no source root under {extract_dir}")
    full = [p for p in candidates if p.name.endswith("-full")]
    return full[0] if full else candidates[0]


def load_pin(path: Path = DEFAULT_PIN) -> dict:
    if not path.is_file():
        return {
            "upstream_repo": UPSTREAM,
            "tag": None,
            "checked_at": None,
            "patch": "patches/0001-no-sponsored-messages.patch",
            "patch_status": "unknown",
            "notes": "",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_pin(data: dict, path: Path = DEFAULT_PIN) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"updated pin: {path} -> {data.get('tag')}")


def rel_to_repo(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def github_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        if "\n" in value:
            f.write(f"{key}<<EOF\n{value}\nEOF\n")
        else:
            f.write(f"{key}={value}\n")


def fetch_source(tag: str, work: Path, keep_archive: bool = True) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    ver = version_from_tag(tag)
    archive = work / f"tdesktop-{ver}.tar.gz"
    extract_dir = work / f"extract-{ver}"
    src = work / "src"

    if src.exists() or src.is_symlink():
        if src.is_dir() and not src.is_symlink():
            shutil.rmtree(src)
        else:
            src.unlink()

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    if not archive.exists() or archive.stat().st_size < 1024:
        last_err: Exception | None = None
        for url in source_urls(tag):
            try:
                http_download(url, archive)
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                log(f"failed: {e}")
        if last_err is not None:
            raise CliError(f"could not download source for {tag}: {last_err}")

    log(f"extract {archive.name}")
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(extract_dir)

    root = find_source_root(extract_dir)
    shutil.move(str(root), str(src))
    shutil.rmtree(extract_dir, ignore_errors=True)

    if not keep_archive and archive.exists():
        archive.unlink()

    (work / "VERSION").write_text(tag + "\n", encoding="utf-8")
    log(f"source ready: {src}")
    return src


def apply_patch(
    src: Path,
    patch: Path,
    *,
    reverse: bool = False,
    check_only: bool = False,
) -> None:
    if not patch.is_file():
        raise CliError(f"patch not found: {patch}")
    if not src.is_dir():
        raise CliError(f"source dir not found: {src}")

    cmd = ["git", "apply", "--verbose", "--whitespace=nowarn"]
    if check_only:
        cmd.append("--check")
    if reverse:
        cmd.append("--reverse")
    cmd.append(str(patch.resolve()))

    try:
        run(cmd, cwd=src)
    except subprocess.CalledProcessError as e:
        log("git apply failed, trying patch(1)")
        pcmd = ["patch", "-p1", "-i", str(patch.resolve())]
        if check_only:
            pcmd.insert(1, "--dry-run")
        if reverse:
            pcmd.insert(1, "-R")
        try:
            run(pcmd, cwd=src)
        except (subprocess.CalledProcessError, FileNotFoundError) as e2:
            raise CliError(
                "patch failed. Upstream likely changed sponsored_messages.cpp.\n"
                f"  patch: {patch}\n"
                f"  git apply: {e}\n"
                f"  patch: {e2}"
            ) from e2

    action = "checked" if check_only else ("reversed" if reverse else "applied")
    log(f"patch {action}: {patch.name}")


def _replace_function_body(src: str, signature: str) -> tuple[str, bool]:
    """Replace a whole C++ method body with `return false;`."""
    # Match from signature line through its closing brace at column 0.
    # Body may contain nested braces; track depth after the opening `{` of the method.
    pat = re.compile(
        re.escape(signature) + r"[ \t]*\{",
        re.MULTILINE,
    )
    m = pat.search(src)
    if not m:
        return src, False

    start = m.start()
    i = m.end() - 1  # position of '{'
    depth = 0
    end = None
    while i < len(src):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end is None:
        return src, False

    replacement = f"{signature} {{\n\treturn false;\n}}"
    return src[:start] + replacement + src[end:], True


def heal_sponsored_source(cpp_text: str) -> tuple[str, list[str]]:
    """Force no-ads by short-circuiting the three entry points."""
    signatures = [
        "bool SponsoredMessages::canHaveFor(not_null<History*> history) const",
        "bool SponsoredMessages::canHaveFor(not_null<HistoryItem*> item) const",
        "bool SponsoredMessages::isTopBarFor(not_null<History*> history) const",
    ]
    out = cpp_text
    done: list[str] = []
    for sig in signatures:
        out, ok = _replace_function_body(out, sig)
        if ok:
            done.append(sig)
    if len(done) != len(signatures):
        missing = [s for s in signatures if s not in done]
        raise CliError(
            "auto-heal could not find all sponsored entry points:\n  - "
            + "\n  - ".join(missing)
        )
    return out, done


def generate_unified_patch(original: str, patched: str, relpath: str) -> str:
    a = original.splitlines(keepends=True)
    b = patched.splitlines(keepends=True)
    # Ensure trailing newline consistency for diff
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    diff = difflib.unified_diff(
        a,
        b,
        fromfile=f"a/{relpath}",
        tofile=f"b/{relpath}",
    )
    text = "".join(diff)
    if not text.endswith("\n"):
        text += "\n"
    if not text.strip():
        raise CliError("generated empty patch (source already no-ads?)")
    return text


def auto_heal_patch(src: Path, patch_path: Path) -> str:
    """Rewrite sponsored_messages.cpp entry points and regenerate patch file."""
    target = src / SPONSORED_REL
    if not target.is_file():
        raise CliError(f"missing {SPONSORED_REL} under {src}")

    original = target.read_text(encoding="utf-8", errors="replace")
    # normalize to LF for stable patch generation
    original_lf = original.replace("\r\n", "\n")
    healed, done = heal_sponsored_source(original_lf)
    log("auto-heal rewrote:")
    for s in done:
        log(f"  - {s}")

    rel = SPONSORED_REL.as_posix()
    patch_text = generate_unified_patch(original_lf, healed, rel)
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    log(f"regenerated patch: {patch_path}")

    # Verify regenerated patch applies cleanly on a fresh copy of original
    # (file on disk is still original)
    target.write_text(original_lf, encoding="utf-8", newline="\n")
    apply_patch(src, patch_path, check_only=True)
    return patch_text


def write_release_notes(path: Path, release: dict, tag: str, *, healed: bool) -> None:
    body = release.get("body") or ""
    mode = "auto-healed and regenerated" if healed else "existing patch applies"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## Upstream {tag}\n\n"
        f"- Official: {release.get('html_url')}\n"
        f"- Published: {release.get('published_at')}\n"
        f"- Patch: `patches/0001-no-sponsored-messages.patch` — **{mode}**\n\n"
        f"### Official changelog\n\n{body}\n\n"
        f"### This repo\n\n"
        f"Pure GitHub auto-follow of official Telegram Desktop.\n"
        f"Only disables Sponsored Messages (client-side).\n"
        f"No Windows binary is built by CI.\n\n"
        f"```bash\n"
        f"python cli/tdesktop_noads.py prepare --tag {tag}\n"
        f"```\n",
        encoding="utf-8",
    )


def write_failure(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upstream_release(tag: str | None = None) -> dict:
    if tag:
        tag = normalize_tag(tag)
        data = http_json(f"https://api.github.com/repos/{UPSTREAM}/releases/tags/{tag}")
    else:
        data = http_json(f"https://api.github.com/repos/{UPSTREAM}/releases/latest")
    assert isinstance(data, dict)
    return data


def cmd_latest(_: argparse.Namespace) -> int:
    data = upstream_release(None)
    print(
        json.dumps(
            {
                "tag": data["tag_name"],
                "name": data.get("name"),
                "published_at": data.get("published_at"),
                "html_url": data.get("html_url"),
                "body": (data.get("body") or "")[:500],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    tag = normalize_tag(args.tag)
    fetch_source(tag, Path(args.work).resolve(), keep_archive=not args.no_keep_archive)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    work = Path(args.work).resolve()
    src = Path(args.src).resolve() if args.src else work / "src"
    patch = Path(args.patch).resolve() if args.patch else DEFAULT_PATCH
    apply_patch(src, patch, reverse=args.reverse, check_only=args.check)
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    tag = normalize_tag(args.tag)
    work = Path(args.work).resolve()
    patch = Path(args.patch).resolve() if args.patch else DEFAULT_PATCH
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    apply_patch(src, patch, check_only=False)
    log(f"prepare done: {tag} -> {src}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    tag = normalize_tag(args.tag)
    work = Path(args.work).resolve()
    patch = Path(args.patch).resolve() if args.patch else DEFAULT_PATCH
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    apply_patch(src, patch, check_only=True)
    if not args.dry_run_only:
        apply_patch(src, patch, check_only=False)
    log(f"OK: patch applies on {tag}")
    github_output("patch_ok", "true")
    github_output("tag", tag)
    return 0


def cmd_heal(args: argparse.Namespace) -> int:
    """Regenerate patch against a tag (CI / recovery)."""
    tag = normalize_tag(args.tag)
    work = Path(args.work).resolve()
    patch = Path(args.patch).resolve() if args.patch else DEFAULT_PATCH
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    auto_heal_patch(src, patch)
    log(f"heal done for {tag}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    work = Path(args.work).resolve()
    pin = load_pin(Path(args.pin).resolve() if args.pin else DEFAULT_PIN)
    work_pin = work / "VERSION"
    latest = normalize_tag(None)
    current = pin.get("tag")
    work_tag = work_pin.read_text(encoding="utf-8").strip() if work_pin.is_file() else None
    print(
        json.dumps(
            {
                "latest_upstream": latest,
                "repo_pin": current,
                "work_pin": work_tag,
                "up_to_date": current == latest if current else False,
                "source_exists": (work / "src").is_dir(),
                "patch": rel_to_repo(DEFAULT_PATCH),
                "patch_exists": DEFAULT_PATCH.is_file(),
                "patch_status": pin.get("patch_status"),
                "work": str(work),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_follow(args: argparse.Namespace) -> int:
    """Pure-CI entry: follow official release, apply or auto-heal patch, update pin."""
    pin_path = Path(args.pin).resolve() if args.pin else DEFAULT_PIN
    pin = load_pin(pin_path)
    patch = Path(args.patch).resolve() if args.patch else DEFAULT_PATCH
    work = Path(args.work).resolve()

    release = upstream_release(args.tag)
    tag = normalize_tag(release["tag_name"])
    pinned = pin.get("tag")

    github_output("tag", tag)
    github_output("pinned", pinned or "")
    github_output("html_url", release.get("html_url") or "")
    github_output("published_at", release.get("published_at") or "")

    if pinned == tag and not args.force:
        log(f"already on {tag}, nothing to do")
        github_output("skipped", "true")
        github_output("changed", "false")
        github_output("patch_ok", "true")
        github_output("healed", "false")
        if args.touch_checked_at:
            pin["checked_at"] = utc_now()
            save_pin(pin, pin_path)
            github_output("changed", "true")
        return 0

    log(f"follow: {pinned or '(none)'} -> {tag}")
    github_output("skipped", "false")
    healed = False
    heal_note = "existing patch applies"

    try:
        src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
        try:
            apply_patch(src, patch, check_only=True)
        except CliError as apply_err:
            if not args.auto_heal:
                raise
            log(f"patch apply failed, auto-heal: {apply_err}")
            auto_heal_patch(src, patch)
            healed = True
            heal_note = "auto-healed (patch regenerated)"

        if not args.dry_run_only:
            # re-fetch clean tree if we only checked, or apply after heal
            if healed:
                # auto_heal left original on disk and verified check; apply for real if needed
                apply_patch(src, patch, check_only=False)
            else:
                apply_patch(src, patch, check_only=False)
    except CliError as e:
        fail = {
            "tag": tag,
            "pinned": pinned,
            "error": str(e),
            "html_url": release.get("html_url"),
            "checked_at": utc_now(),
            "auto_heal": bool(args.auto_heal),
        }
        write_failure(work / "follow-failure.json", fail)
        github_output("changed", "false")
        github_output("patch_ok", "false")
        github_output("healed", "false")
        github_output("error", str(e).replace("\n", " | ")[:1000])
        print(f"error: {e}", file=sys.stderr)
        return 2

    pin = {
        "upstream_repo": UPSTREAM,
        "tag": tag,
        "checked_at": utc_now(),
        "published_at": release.get("published_at"),
        "html_url": release.get("html_url"),
        "patch": rel_to_repo(patch),
        "patch_status": "ok",
        "healed": healed,
        "notes": f"Auto-followed {tag}; {heal_note}.",
    }
    save_pin(pin, pin_path)
    write_release_notes(work / "release-notes.md", release, tag, healed=healed)

    github_output("changed", "true")
    github_output("patch_ok", "true")
    github_output("healed", "true" if healed else "false")
    github_output("release_notes", str(work / "release-notes.md"))
    log(f"follow OK: pinned {tag} (healed={healed})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tdesktop-noads",
        description="Pure-GitHub auto-follow for official Telegram Desktop + no-ads patch.",
    )
    p.add_argument("--work", default=str(DEFAULT_WORK))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("latest", help="show latest upstream release")
    s.set_defaults(func=cmd_latest)

    s = sub.add_parser("fetch", help="download + extract upstream source")
    s.add_argument("--tag", default=None)
    s.add_argument("--no-keep-archive", action="store_true")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("apply", help="apply / check / reverse patch")
    s.add_argument("--src", default=None)
    s.add_argument("--patch", default=None)
    s.add_argument("--check", action="store_true")
    s.add_argument("--reverse", action="store_true")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("prepare", help="fetch + apply (local build helper)")
    s.add_argument("--tag", default=None)
    s.add_argument("--patch", default=None)
    s.add_argument("--no-keep-archive", action="store_true")
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("check", help="verify patch applies")
    s.add_argument("--tag", default=None)
    s.add_argument("--patch", default=None)
    s.add_argument("--dry-run-only", action="store_true")
    s.add_argument("--no-keep-archive", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("heal", help="regenerate patch against a tag")
    s.add_argument("--tag", default=None)
    s.add_argument("--patch", default=None)
    s.add_argument("--no-keep-archive", action="store_true")
    s.set_defaults(func=cmd_heal)

    s = sub.add_parser("status", help="pin vs upstream")
    s.add_argument("--pin", default=None)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("follow", help="CI entry: follow upstream, auto-heal if needed")
    s.add_argument("--tag", default=None)
    s.add_argument("--patch", default=None)
    s.add_argument("--pin", default=None)
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run-only", action="store_true", help="only check/heal patch, skip final apply")
    s.add_argument("--no-keep-archive", action="store_true")
    s.add_argument("--auto-heal", action="store_true", help="regenerate patch when apply fails")
    s.add_argument("--touch-checked-at", action="store_true")
    s.set_defaults(func=cmd_follow)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"error: command failed: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
