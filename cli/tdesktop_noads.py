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
DEFAULT_PATCHES_DIR = REPO_ROOT / "patches"
DEFAULT_WORK = REPO_ROOT / "work"
DEFAULT_PIN = REPO_ROOT / "versions" / "current.json"
UPSTREAM = "telegramdesktop/tdesktop"
SPONSORED_REL = Path("Telegram/SourceFiles/data/components/sponsored_messages.cpp")
MAIN_SESSION_REL = Path("Telegram/SourceFiles/main/main_session.cpp")
PEER_VALUES_REL = Path("Telegram/SourceFiles/data/data_peer_values.cpp")
EXPERIMENTAL_REL = Path("Telegram/SourceFiles/settings/settings_experimental.cpp")
NOADS_SETTINGS_H = Path("Telegram/SourceFiles/settings/settings_noads.h")
NOADS_SETTINGS_CPP = Path("Telegram/SourceFiles/settings/settings_noads.cpp")
CMAKE_REL = Path("Telegram/CMakeLists.txt")
SETTINGS_MAIN_REL = Path("Telegram/SourceFiles/settings/sections/settings_main.cpp")
USER_AGENT = "tdesktop-noads-cli/0.5 (+https://github.com/vcshixin/tdesktop-noads)"


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


def github_headers(*, accept_json: bool = True) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if accept_json:
        headers["Accept"] = "application/vnd.github+json"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=github_headers())
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
    req = urllib.request.Request(url, headers=github_headers(accept_json=False))
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
        raise CliError(
            "patch failed exact git-apply validation; upstream or patch content changed.\n"
            f"  patch: {patch}\n"
            f"  git apply: {e}"
        ) from e

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


def _ensure_include(src: str, include_line: str) -> str:
    if include_line in src:
        return src
    m = re.search(r'#include "base/[^"]+"\n', src)
    if m:
        return src[: m.end()] + include_line + src[m.end() :]
    m = re.search(r'#include "[^"]+"\n', src)
    if m:
        return src[: m.end()] + include_line + src[m.end() :]
    return include_line + src


def heal_sponsored_source(cpp_text: str) -> tuple[str, list[str]]:
    """Inject disable-ads option + guards into sponsored_messages entry points."""
    done: list[str] = []
    out = _ensure_include(cpp_text, '#include "base/options.h"\n')

    option_block = (
        "\n"
        "const char kOptionNoadsDisableAds[] = \"noads-disable-ads\";\n"
        "\n"
        "base::options::toggle OptionNoadsDisableAds({\n"
        "\t.id = kOptionNoadsDisableAds,\n"
        "\t.name = \"禁用赞助广告\",\n"
        "\t.description = \"关闭频道与机器人对话中的赞助消息（仅本客户端，默认开启）。\",\n"
        "\t.defaultValue = true,\n"
        "});\n"
    )
    if "kOptionNoadsDisableAds" not in out:
        anchor = "namespace Data {\nnamespace {\n"
        if anchor not in out:
            raise CliError("sponsored: namespace Data anchor missing")
        out = out.replace(anchor, anchor + option_block, 1)
        done.append("OptionNoadsDisableAds")
    else:
        done.append("OptionNoadsDisableAds(exists)")

    guard = "\tif (OptionNoadsDisableAds.value()) {\n\t\treturn false;\n\t}\n"
    signatures = [
        "bool SponsoredMessages::canHaveFor(not_null<History*> history) const",
        "bool SponsoredMessages::canHaveFor(not_null<HistoryItem*> item) const",
        "bool SponsoredMessages::isTopBarFor(not_null<History*> history) const",
    ]
    for sig in signatures:
        pat = re.compile(re.escape(sig) + r"[ \t]*\{", re.MULTILINE)
        m = pat.search(out)
        if not m:
            raise CliError(f"auto-heal missing {sig}")
        brace = m.end() - 1
        window = out[brace : brace + 120]
        if "OptionNoadsDisableAds.value()" in window:
            done.append(sig + "(exists)")
            continue
        nl = out.find("\n", brace)
        if nl < 0:
            raise CliError(f"no newline after {sig}")
        out = out[: nl + 1] + guard + out[nl + 1 :]
        done.append(sig)
    return out, done


def generate_unified_patch(original: str, patched: str, relpath: str) -> str:
    a = original.splitlines(keepends=True)
    b = patched.splitlines(keepends=True)
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
        raise CliError("generated empty patch (source already patched?)")
    return text


def auto_heal_patch(src: Path, patch_path: Path) -> str:
    """Regenerate no-ads (settings-aware) patch."""
    target = src / SPONSORED_REL
    if not target.is_file():
        raise CliError(f"missing {SPONSORED_REL} under {src}")

    original = target.read_text(encoding="utf-8", errors="replace")
    original_lf = original.replace("\r\n", "\n")
    healed, done = heal_sponsored_source(original_lf)
    log("auto-heal no-ads rewrote:")
    for s in done:
        log(f"  - {s}")

    patch_text = generate_unified_patch(original_lf, healed, SPONSORED_REL.as_posix())
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    log(f"regenerated patch: {patch_path}")

    target.write_text(original_lf, encoding="utf-8", newline="\n")
    apply_patch(src, patch_path, check_only=True)
    return patch_text


def heal_local_premium_sources(main_session: str, peer_values: str) -> tuple[str, str, list[str]]:
    """Inject localPremium option + guards (settings-aware)."""
    done: list[str] = []

    ms = _ensure_include(main_session, '#include "base/options.h"\n')
    option_block = (
        "\n"
        "const char kOptionNoadsLocalPremium[] = \"noads-local-premium\";\n"
        "\n"
        "base::options::toggle OptionNoadsLocalPremium({\n"
        "\t.id = kOptionNoadsLocalPremium,\n"
        "\t.name = \"本地大会员\",\n"
        "\t.description = \"仅在本客户端伪装为 Premium，不解锁服务器校验功能（上传上限等仍无效）。修改后建议重启。\",\n"
        "\t.defaultValue = true,\n"
        "\t.restartRequired = true,\n"
        "});\n"
        "\n"
    )
    if "kOptionNoadsLocalPremium" not in ms:
        anchor = "namespace Main {\n"
        if anchor not in ms:
            raise CliError("main_session: namespace Main missing")
        ms = ms.replace(anchor, option_block + anchor, 1)
        done.append("OptionNoadsLocalPremium")
    else:
        done.append("OptionNoadsLocalPremium(exists)")

    sig = "bool Session::premium() const"
    pat = re.compile(re.escape(sig) + r"[ \t]*\{", re.MULTILINE)
    m = pat.search(ms)
    if not m:
        raise CliError("auto-heal could not locate Session::premium()")
    brace = m.end() - 1
    window = ms[brace : brace + 160]
    if "OptionNoadsLocalPremium.value()" not in window:
        nl = ms.find("\n", brace)
        guard = "\tif (OptionNoadsLocalPremium.value()) {\n\t\treturn true;\n\t}\n"
        ms = ms[: nl + 1] + guard + ms[nl + 1 :]
        done.append("Session::premium")
    else:
        done.append("Session::premium(exists)")

    pv = _ensure_include(peer_values, '#include "base/options.h"\n')
    old_am = (
        "rpl::producer<bool> AmPremiumValue(not_null<Main::Session*> session) {\n"
        "\treturn PeerPremiumValue(session->user());\n"
        "}"
    )
    new_am = (
        "rpl::producer<bool> AmPremiumValue(not_null<Main::Session*> session) {\n"
        "\tif (base::options::value<bool>(\"noads-local-premium\")) {\n"
        "\t\treturn rpl::single(true);\n"
        "\t}\n"
        "\treturn PeerPremiumValue(session->user());\n"
        "}"
    )
    if old_am in pv:
        pv = pv.replace(old_am, new_am, 1)
        done.append("AmPremiumValue")
    elif "noads-local-premium" in pv and "AmPremiumValue" in pv:
        done.append("AmPremiumValue(exists)")
    else:
        sig2 = "rpl::producer<bool> AmPremiumValue(not_null<Main::Session*> session)"
        pat2 = re.compile(re.escape(sig2) + r"[ \t]*\{", re.MULTILINE)
        m2 = pat2.search(pv)
        if not m2:
            raise CliError("auto-heal could not locate AmPremiumValue()")
        start = m2.start()
        i = m2.end() - 1
        depth = 0
        endpos = None
        while i < len(pv):
            if pv[i] == "{":
                depth += 1
            elif pv[i] == "}":
                depth -= 1
                if depth == 0:
                    endpos = i + 1
                    break
            i += 1
        if endpos is None:
            raise CliError("AmPremiumValue brace match failed")
        pv = pv[:start] + new_am + pv[endpos:]
        done.append("AmPremiumValue")

    return ms, pv, done


def auto_heal_local_premium_patch(src: Path, patch_path: Path) -> str:
    f1 = src / MAIN_SESSION_REL
    f2 = src / PEER_VALUES_REL
    if not f1.is_file() or not f2.is_file():
        raise CliError("missing main_session.cpp or data_peer_values.cpp")

    o1 = f1.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    o2 = f2.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    n1, n2, done = heal_local_premium_sources(o1, o2)
    log("auto-heal localPremium rewrote:")
    for s in done:
        log(f"  - {s}")

    patch_text = generate_unified_patch(o1, n1, MAIN_SESSION_REL.as_posix())
    patch_text += generate_unified_patch(o2, n2, PEER_VALUES_REL.as_posix())
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    log(f"regenerated patch: {patch_path}")

    f1.write_text(o1, encoding="utf-8", newline="\n")
    f2.write_text(o2, encoding="utf-8", newline="\n")
    apply_patch(src, patch_path, check_only=True)
    return patch_text


def _noads_settings_h_text() -> str:
    return (
        "/*\n"
        "This file is part of tdesktop-noads patches for Telegram Desktop.\n"
        "*/\n"
        "#pragma once\n"
        "\n"
        "#include \"settings/settings_common_session.h\"\n"
        "\n"
        "namespace Settings {\n"
        "\n"
        "class NoAds : public Section<NoAds> {\n"
        "public:\n"
        "\tNoAds(\n"
        "\t\tQWidget *parent,\n"
        "\t\tnot_null<Window::SessionController*> controller);\n"
        "\n"
        "\t[[nodiscard]] rpl::producer<QString> title() override;\n"
        "\n"
        "private:\n"
        "\tvoid setupContent();\n"
        "\n"
        "};\n"
        "\n"
        "[[nodiscard]] Type NoAdsId();\n"
        "\n"
        "} // namespace Settings\n"
    )


def _noads_settings_cpp_text() -> str:
    return (
        "/*\n"
        "This file is part of tdesktop-noads patches for Telegram Desktop.\n"
        "*/\n"
        "#include \"settings/settings_noads.h\"\n"
        "\n"
        "#include \"base/options.h\"\n"
        "#include \"base/timer.h\"\n"
        "#include \"core/application.h\"\n"
        "#include \"lang/lang_keys.h\"\n"
        "#include \"settings/settings_common.h\"\n"
        "#include \"styles/style_layers.h\"\n"
        "#include \"styles/style_menu_icons.h\"\n"
        "#include \"styles/style_settings.h\"\n"
        "#include \"ui/boxes/confirm_box.h\"\n"
        "#include \"ui/vertical_list.h\"\n"
        "#include \"ui/widgets/buttons.h\"\n"
        "#include \"ui/widgets/labels.h\"\n"
        "#include \"ui/wrap/vertical_layout.h\"\n"
        "#include \"window/window_session_controller.h\"\n"
        "#include \"window/window_controller.h\"\n"
        "\n"
        "namespace Settings {\n"
        "namespace {\n"
        "\n"
        "void AddNoadsToggle(\n"
        "\t\tnot_null<Window::Controller*> window,\n"
        "\t\tnot_null<Ui::VerticalLayout*> container,\n"
        "\t\tconst char *optionId) {\n"
        "\tauto &option = base::options::lookup<bool>(optionId);\n"
        "\tconst auto name = option.name().isEmpty()\n"
        "\t\t? QString::fromUtf8(optionId)\n"
        "\t\t: option.name();\n"
        "\tconst auto description = option.description();\n"
        "\n"
        "\tUi::AddSkip(container, st::settingsCheckboxesSkip);\n"
        "\n"
        "\tconst auto toggles = container->lifetime().make_state<rpl::event_stream<bool>>();\n"
        "\tconst auto button = container->add(object_ptr<Button>(\n"
        "\t\tcontainer,\n"
        "\t\trpl::single(name),\n"
        "\t\tst::settingsButtonNoIcon\n"
        "\t))->toggleOn(toggles->events_starting_with(option.value()));\n"
        "\n"
        "\tconst auto restarter = option.restartRequired()\n"
        "\t\t? button->lifetime().make_state<base::Timer>()\n"
        "\t\t: nullptr;\n"
        "\tif (restarter) {\n"
        "\t\trestarter->setCallback([=] {\n"
        "\t\t\twindow->show(Ui::MakeConfirmBox({\n"
        "\t\t\t\t.text = tr::lng_settings_need_restart(),\n"
        "\t\t\t\t.confirmed = [] { Core::Restart(); },\n"
        "\t\t\t\t.confirmText = tr::lng_settings_restart_now(),\n"
        "\t\t\t\t.cancelText = tr::lng_settings_restart_later(),\n"
        "\t\t\t}));\n"
        "\t\t});\n"
        "\t}\n"
        "\n"
        "\tbutton->toggledChanges(\n"
        "\t) | rpl::on_next([=, &option](bool toggled) {\n"
        "\t\tif (option.value() == toggled) {\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\toption.set(toggled);\n"
        "\t\tif (restarter) {\n"
        "\t\t\trestarter->callOnce(st::settingsButtonNoIcon.toggle.duration);\n"
        "\t\t}\n"
        "\t}, button->lifetime());\n"
        "\n"
        "\tif (!description.isEmpty()) {\n"
        "\t\tUi::AddSkip(container, st::settingsCheckboxesSkip);\n"
        "\t\tUi::AddDividerText(container, rpl::single(description));\n"
        "\t\tUi::AddSkip(container, st::settingsCheckboxesSkip);\n"
        "\t}\n"
        "}\n"
        "\n"
        "} // namespace\n"
        "\n"
        "NoAds::NoAds(\n"
        "\tQWidget *parent,\n"
        "\tnot_null<Window::SessionController*> controller)\n"
        ": Section(parent, controller) {\n"
        "\tsetupContent();\n"
        "}\n"
        "\n"
        "rpl::producer<QString> NoAds::title() {\n"
        "\treturn rpl::single(u\"去广告与本地会员\"_q);\n"
        "}\n"
        "\n"
        "void NoAds::setupContent() {\n"
        "\tconst auto content = Ui::CreateChild<Ui::VerticalLayout>(this);\n"
        "\tconst auto window = &controller()->window();\n"
        "\n"
        "\tUi::AddSkip(content);\n"
        "\tUi::AddSubsectionTitle(\n"
        "\t\tcontent,\n"
        "\t\trpl::single(u\"tdesktop-noads\"_q));\n"
        "\n"
        "\tcontent->add(\n"
        "\t\tobject_ptr<Ui::FlatLabel>(\n"
        "\t\t\tcontent,\n"
        "\t\t\trpl::single(\n"
        "\t\t\t\tu\"以下开关仅影响本客户端。本地大会员不能解锁服务器校验的会员权益（例如更大上传限制）。\"_q),\n"
        "\t\t\tst::boxLabel),\n"
        "\t\tst::defaultBoxDividerLabelPadding);\n"
        "\n"
        "\tUi::AddSkip(content);\n"
        "\tUi::AddDivider(content);\n"
        "\tUi::AddSkip(content);\n"
        "\n"
        "\tUi::AddSubsectionTitle(\n"
        "\t\tcontent,\n"
        "\t\trpl::single(u\"功能开关\"_q));\n"
        "\n"
        "\tAddNoadsToggle(window, content, \"noads-disable-ads\");\n"
        "\tAddNoadsToggle(window, content, \"noads-local-premium\");\n"
        "\n"
        "\tUi::AddSkip(content);\n"
        "\tUi::AddDividerText(\n"
        "\t\tcontent,\n"
        "\t\trpl::single(\n"
        "\t\t\tu\"非官方构建。设置保存在本机实验选项配置中，可随时开关。\"_q));\n"
        "\n"
        "\tUi::ResizeFitChild(this, content);\n"
        "}\n"
        "\n"
        "Type NoAdsId() {\n"
        "\treturn NoAds::Id();\n"
        "}\n"
        "\n"
        "} // namespace Settings\n"
    )


def heal_cmake_source(cmake: str) -> tuple[str, list[str]]:
    done: list[str] = []
    if "settings/settings_noads.cpp" in cmake:
        return cmake, ["cmake(exists)"]
    marker = "    settings/settings_experimental.h\n"
    if marker not in cmake:
        raise CliError("cmake: experimental entries missing")
    cmake = cmake.replace(
        marker,
        marker
        + "    settings/settings_noads.cpp\n"
        + "    settings/settings_noads.h\n",
        1,
    )
    done.append("cmake add settings_noads")
    return cmake, done


def heal_settings_main_source(main_cpp: str) -> tuple[str, list[str]]:
    done: list[str] = []
    out = main_cpp
    if '#include "settings/settings_noads.h"' not in out:
        anchor = '#include "settings/settings_power_saving.h"\n'
        if anchor not in out:
            m = re.search(r'#include "settings/[^"]+"\n', out)
            if not m:
                raise CliError("settings_main: no settings includes")
            out = out[: m.end()] + '#include "settings/settings_noads.h"\n' + out[m.end() :]
        else:
            out = out.replace(anchor, anchor + '#include "settings/settings_noads.h"\n', 1)
        done.append("include settings_noads.h")
    else:
        done.append("include(exists)")

    if "NoAdsId()" in out:
        done.append("menu button(exists)")
        return out, done

    btn = (
        "\n"
        "\tbuilder.addSectionButton({\n"
        "\t\t.title = rpl::single(u\"去广告与本地会员\"_q),\n"
        "\t\t.targetSection = NoAdsId(),\n"
        "\t\t.icon = { &st::menuIconFave },\n"
        "\t\t.keywords = {\n"
        "\t\t\tu\"ads\"_q,\n"
        "\t\t\tu\"premium\"_q,\n"
        "\t\t\tu\"noads\"_q,\n"
        "\t\t\tu\"赞助\"_q,\n"
        "\t\t\tu\"会员\"_q,\n"
        "\t\t},\n"
        "\t});\n"
    )
    anchor = (
        "\tbuilder.addSectionButton({\n"
        "\t\t.title = tr::lng_settings_advanced(),\n"
        "\t\t.targetSection = AdvancedId(),\n"
    )
    idx = out.find(anchor)
    if idx < 0:
        raise CliError("settings_main: Advanced section button missing")
    j = out.find("});", idx)
    if j < 0:
        raise CliError("settings_main: Advanced button end missing")
    j = j + 3
    out = out[:j] + btn + out[j:]
    done.append("menu button NoAds")
    return out, done


def auto_heal_settings_patch(src: Path, patch_path: Path) -> str:
    """Regenerate dedicated Chinese NoAds settings page patch."""
    done_all: list[str] = []
    parts: list[str] = []

    h_text = _noads_settings_h_text()
    c_text = _noads_settings_cpp_text()
    parts.append(generate_unified_patch("", h_text, NOADS_SETTINGS_H.as_posix()))
    parts.append(generate_unified_patch("", c_text, NOADS_SETTINGS_CPP.as_posix()))
    done_all += ["settings_noads.h", "settings_noads.cpp"]

    cmake_path = src / CMAKE_REL
    main_path = src / SETTINGS_MAIN_REL
    if not cmake_path.is_file() or not main_path.is_file():
        raise CliError("missing CMakeLists.txt or settings_main.cpp")

    o_cmake = cmake_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    o_main = main_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    n_cmake, d1 = heal_cmake_source(o_cmake)
    n_main, d2 = heal_settings_main_source(o_main)
    done_all += d1 + d2
    parts.append(generate_unified_patch(o_cmake, n_cmake, CMAKE_REL.as_posix()))
    parts.append(generate_unified_patch(o_main, n_main, SETTINGS_MAIN_REL.as_posix()))

    log("auto-heal NoAds settings page rewrote:")
    for s in done_all:
        log(f"  - {s}")

    patch_text = "".join(parts)
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    log(f"regenerated patch: {patch_path}")

    cmake_path.write_text(o_cmake, encoding="utf-8", newline="\n")
    main_path.write_text(o_main, encoding="utf-8", newline="\n")
    for rel in (NOADS_SETTINGS_H, NOADS_SETTINGS_CPP):
        fp = src / rel
        if fp.is_file():
            fp.unlink()
    apply_patch(src, patch_path, check_only=True)
    return patch_text


def regenerate_ai_patches(src: Path) -> None:
    # fetch_source() records the selected upstream tag next to its src/ tree.
    # GitHub Actions invokes this helper on a checkout instead, so fall back to
    # the current pin and finally the tag embedded in the source version file.
    version_file = src.parent / "VERSION"
    tag: str | None = None
    if version_file.is_file():
        tag = version_file.read_text(encoding="utf-8").strip()
    if not tag and (src / ".git").exists():
        described = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=src,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if described.returncode == 0:
            tag = described.stdout.strip()
    if not tag:
        version_info = src / "Telegram" / "build" / "version"
        if version_info.is_file():
            match = re.search(
                r"^AppVersionOriginal\s+([0-9.]+)",
                version_info.read_text(encoding="utf-8", errors="replace"),
                re.MULTILINE,
            )
            if match:
                tag = match.group(1)
    if not tag and DEFAULT_PIN.is_file():
        tag = str(load_pin(DEFAULT_PIN).get("tag") or "")
    if not tag:
        raise CliError("cannot determine upstream tag for AI patch regeneration")
    generator = REPO_ROOT / "scripts" / "gen_ai_patches.py"
    if not generator.is_file():
        raise CliError(f"missing AI patch generator: {generator}")
    run([sys.executable, str(generator), "--tag", normalize_tag(tag)], cwd=REPO_ROOT)


def auto_heal_named_patch(src: Path, patch_path: Path) -> str:
    name = patch_path.name.lower()
    if "sponsored" in name or name.startswith("0001"):
        return auto_heal_patch(src, patch_path)
    if "premium" in name or name.startswith("0002"):
        return auto_heal_local_premium_patch(src, patch_path)
    if name.startswith(("0003", "0004", "0005")):
        regenerate_ai_patches(src)
        return patch_path.read_text(encoding="utf-8")
    raise CliError(f"no auto-heal strategy for {patch_path.name}")


def list_default_patches() -> list[Path]:
    return sorted(DEFAULT_PATCHES_DIR.glob("*.patch"))


def apply_all_patches(
    src: Path,
    patches: list[Path] | None = None,
    *,
    check_only: bool = False,
    heal: bool = False,
) -> bool:
    """Apply every patch. Returns True if any patch was healed/regenerated."""
    patches = patches or list_default_patches()
    if not patches:
        raise CliError("no patches found")
    healed_any = False
    for patch in patches:
        try:
            apply_patch(src, patch, check_only=check_only)
        except CliError:
            if not heal:
                raise
            log(f"heal then re-apply: {patch.name}")
            auto_heal_named_patch(src, patch)
            apply_patch(src, patch, check_only=check_only)
            healed_any = True
        if check_only:
            # Later patches are generated against the tree produced by earlier
            # patches, so validation must advance the disposable source tree.
            apply_patch(src, patch, check_only=False)
    return healed_any


def write_release_notes(path: Path, release: dict, tag: str, *, healed: bool) -> None:
    body = release.get("body") or ""
    mode = "auto-healed and regenerated" if healed else "existing patches apply"
    patches = ", ".join(p.name for p in list_default_patches()) or "(none)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## Upstream {tag}\n\n"
        f"- Official: {release.get('html_url')}\n"
        f"- Published: {release.get('published_at')}\n"
        f"- Patches: `{patches}` — **{mode}**\n\n"
        f"### Features\n\n"
        f"- No Sponsored Messages (client-side)\n"
        f"- Local Premium (client-side UI spoof; server-gated features still need real Premium)\n"
        f"- Chinese settings page: 设置 -> 去广告 / AI / 语音\n"
        f"- Optional OpenAI-compatible LLM translation and custom STT\n\n"
        f"### Official changelog\n\n{body}\n\n"
        f"### Portable build\n\n"
        f"Windows x64 portable zip is produced by `build-windows` workflow and attached here.\n",
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
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    if args.patch:
        apply_patch(src, Path(args.patch).resolve(), check_only=False)
    else:
        apply_all_patches(src, heal=False)
    log(f"prepare done: {tag} -> {src}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    tag = normalize_tag(args.tag)
    work = Path(args.work).resolve()
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    if args.patch:
        apply_patch(src, Path(args.patch).resolve(), check_only=True)
        if not args.dry_run_only:
            apply_patch(src, Path(args.patch).resolve(), check_only=False)
    else:
        apply_all_patches(src, check_only=True, heal=False)
    log(f"OK: patches apply sequentially on {tag}")
    github_output("patch_ok", "true")
    github_output("tag", tag)
    return 0


def cmd_heal(args: argparse.Namespace) -> int:
    """Regenerate patch(es) against a tag (CI / recovery)."""
    tag = normalize_tag(args.tag)
    work = Path(args.work).resolve()
    src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
    if args.patch:
        auto_heal_named_patch(src, Path(args.patch).resolve())
    else:
        for patch in list_default_patches():
            auto_heal_named_patch(src, patch)
    log(f"heal done for {tag}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    work = Path(args.work).resolve()
    pin = load_pin(Path(args.pin).resolve() if args.pin else DEFAULT_PIN)
    work_pin = work / "VERSION"
    latest = normalize_tag(None)
    current = pin.get("tag")
    work_tag = work_pin.read_text(encoding="utf-8").strip() if work_pin.is_file() else None
    patches = [rel_to_repo(p) for p in list_default_patches()]
    print(
        json.dumps(
            {
                "latest_upstream": latest,
                "repo_pin": current,
                "work_pin": work_tag,
                "up_to_date": current == latest if current else False,
                "source_exists": (work / "src").is_dir(),
                "patches": patches,
                "patch_status": pin.get("patch_status"),
                "work": str(work),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_follow(args: argparse.Namespace) -> int:
    """Pure-CI entry: follow official release, apply/heal all patches, update pin."""
    pin_path = Path(args.pin).resolve() if args.pin else DEFAULT_PIN
    pin = load_pin(pin_path)
    work = Path(args.work).resolve()
    patches = (
        [Path(args.patch).resolve()]
        if args.patch
        else list_default_patches()
    )

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
    heal_note = "existing patches apply"

    try:
        src = fetch_source(tag, work, keep_archive=not args.no_keep_archive)
        healed = apply_all_patches(
            src,
            patches,
            check_only=True,
            heal=bool(args.auto_heal),
        )
        if healed:
            heal_note = "auto-healed (one or more patches regenerated)"
    except CliError as e:
        fail = {
            "tag": tag,
            "pinned": pinned,
            "error": str(e),
            "html_url": release.get("html_url"),
            "checked_at": utc_now(),
            "auto_heal": bool(args.auto_heal),
            "patches": [p.name for p in patches],
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
        "patches": [rel_to_repo(p) for p in patches],
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
