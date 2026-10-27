#!/usr/bin/env python3
"""Generate patches/0006-mute-in-fullscreen.patch for tdesktop-noads.

Design notes
------------
* 0003 / 0004 / 0005 are produced by scripts/gen_ai_patches.py.  They *create*
  settings/settings_noads.cpp, noads/noads_ai_options.cpp and the CMake
  entries, and auto-heal may regenerate them at any time.  0006 therefore must
  not be written against raw upstream for those files: it is generated against
  the post-0005 state, reconstructed here from gen_ai_patches.py plus upstream
  CMakeLists.txt.  Regenerating is then always correct, and 0006 never fights
  the other generators.
* Only upstream files are fetched over HTTPS, so this runs without a checkout.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import urllib.request
from pathlib import Path

DEFAULT_TAG = "v7.3.3"
UA = {"User-Agent": "tdesktop-noads"}
ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches"
BASE = ""

NOTIFICATIONS_REL = "Telegram/SourceFiles/platform/win/notifications_manager_win.cpp"
SETTINGS_NOADS_REL = "Telegram/SourceFiles/settings/settings_noads.cpp"
AI_OPTIONS_REL = "Telegram/SourceFiles/noads/noads_ai_options.cpp"
NOTIFY_H_REL = "Telegram/SourceFiles/noads/noads_notify_options.h"
NOTIFY_CPP_REL = "Telegram/SourceFiles/noads/noads_notify_options.cpp"
CMAKE_REL = "Telegram/CMakeLists.txt"

NOTIFY_H = """/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#pragma once

namespace NoAds {
namespace Notify {

inline constexpr auto kMuteInFullscreen = "noads-mute-fullscreen";
inline constexpr auto kMuteSoundOnly = "noads-mute-sound-only";

// Registered from NoAds::Ai::RegisterOptions(): that is the single entry point
// which already existed and is reached from every code path that can touch the
// notification manager. Never call base::options::Lookup with an unregistered
// id - it asserts (Ensures) instead of falling back to a default.
void RegisterOptions();

[[nodiscard]] bool MuteInFullscreen();
[[nodiscard]] bool MuteSoundOnly();

} // namespace Notify
} // namespace NoAds
"""

NOTIFY_CPP = """/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#include "noads/noads_notify_options.h"

#include "base/options.h"

namespace NoAds {
namespace Notify {

base::options::toggle OptionMuteInFullscreen({
	.id = kMuteInFullscreen,
	.name = "全屏时静音",
	.description = "检测到无边框满屏应用（网页全屏 F11 / 视频全屏、游戏窗口化全屏、独占全屏）时抑制 Telegram 通知。",
	.defaultValue = true,
});

base::options::toggle OptionMuteSoundOnly({
	.id = kMuteSoundOnly,
	.name = "仅静音，保留弹窗",
	.description = "开启：全屏时不响铃，但仍弹出通知。关闭：全屏时弹窗与声音一起静默。",
	.defaultValue = false,
});

void RegisterOptions() {
	// ODR-use the options so this translation unit constructs them.
	(void)OptionMuteInFullscreen.value();
	(void)OptionMuteSoundOnly.value();
}

bool MuteInFullscreen() {
	return OptionMuteInFullscreen.value();
}

bool MuteSoundOnly() {
	return OptionMuteSoundOnly.value();
}

} // namespace Notify
} // namespace NoAds
"""

NOTIFY_INCLUDE = '#include "noads/noads_notify_options.h"\n'

NOTIFY_SECTION = """	Ui::AddSubsectionTitle(content, rpl::single(u"全屏通知"_q));

	const auto notifyToggle = AddToggle(
		window,
		content,
		::NoAds::Notify::kMuteInFullscreen);

	const auto notifyWrap = content->add(
		object_ptr<Ui::SlideWrap<Ui::VerticalLayout>>(
			content,
			object_ptr<Ui::VerticalLayout>(content)));
	const auto notifyInner = notifyWrap->entity();

	AddToggle(
		window,
		notifyInner,
		::NoAds::Notify::kMuteSoundOnly);

	notifyWrap->toggle(
		::NoAds::Notify::MuteInFullscreen(),
		anim::type::instant);
	notifyToggle->toggledChanges(
	) | rpl::on_next([=](bool toggled) {
		notifyWrap->toggle(toggled, anim::type::normal);
	}, notifyWrap->lifetime());

	Ui::AddSkip(content, st::settingsCheckboxesSkip);
	Ui::AddDividerText(
		content,
		rpl::single(u"全屏指无边框满屏：网页全屏（F11 / 视频全屏）、游戏窗口化全屏与独占全屏。普通最大化窗口不算全屏，通知行为不变。"_q));

	Ui::AddSkip(content);
	Ui::AddDivider(content);
	Ui::AddSkip(content);
"""

SOUND_OLD = """bool SkipSoundForCustom() {
	QuerySystemNotificationSettings();

	return (UserNotificationState == QUNS_NOT_PRESENT)
		|| (UserNotificationState == QUNS_PRESENTATION_MODE)
		|| (FocusAssistBlocks && Core::App().settings().skipToastsInFocus())
		|| Core::App().screenIsLocked();
}
"""

SOUND_NEW = '''// tdesktop-noads: QUNS_BUSY means "a full-screen application is running" -
// borderless fullscreen windows, F11 / video fullscreen in a browser and
// windowed-borderless games all report it, while a merely maximized window
// reports QUNS_ACCEPTS_NOTIFICATIONS. Upstream only treats
// QUNS_RUNNING_D3D_FULL_SCREEN as fullscreen, so toasts still popped up in
// those cases; and its sound check tested no fullscreen state at all, so sound
// always played while watching video or gaming in fullscreen.
[[nodiscard]] bool NoadsFullscreenActive() {
	return ::NoAds::Notify::MuteInFullscreen()
		&& ((UserNotificationState == QUNS_BUSY)
			|| (UserNotificationState == QUNS_RUNNING_D3D_FULL_SCREEN));
}

bool SkipSoundForCustom() {
	QuerySystemNotificationSettings();

	return (UserNotificationState == QUNS_NOT_PRESENT)
		|| (UserNotificationState == QUNS_PRESENTATION_MODE)
		|| NoadsFullscreenActive()
		|| (FocusAssistBlocks && Core::App().settings().skipToastsInFocus())
		|| Core::App().screenIsLocked();
}
'''

TOAST_OLD = """bool SkipToastForCustom() {
	QuerySystemNotificationSettings();

	return (UserNotificationState == QUNS_PRESENTATION_MODE)
		|| (UserNotificationState == QUNS_RUNNING_D3D_FULL_SCREEN)
		|| (FocusAssistBlocks && Core::App().settings().skipToastsInFocus());
}
"""

TOAST_NEW = '''bool SkipToastForCustom() {
	QuerySystemNotificationSettings();

	// Upstream skipped toasts only for QUNS_RUNNING_D3D_FULL_SCREEN (exclusive
	// Direct3D fullscreen), leaving borderless fullscreen (QUNS_BUSY) popping
	// up. Add it here too, and honour the "mute sound only" choice by keeping
	// the toast.
	const auto noadsToast = NoadsFullscreenActive()
		&& !::NoAds::Notify::MuteSoundOnly();

	return (UserNotificationState == QUNS_PRESENTATION_MODE)
		|| (UserNotificationState == QUNS_RUNNING_D3D_FULL_SCREEN)
		|| noadsToast
		|| (FocusAssistBlocks && Core::App().settings().skipToastsInFocus());
}
'''

REG_ANCHOR = "\t// ODR-use options so they are constructed.\n"
REG_ADDED = (
    "\t// This is the single registration entry point that already existed and is\n"
    "\t// reached from every path that can touch the notification manager, so the\n"
    "\t// notify options are registered here as well.\n"
    "\t::NoAds::Notify::RegisterOptions();\n"
)


def fetch(rel: str) -> str:
    req = urllib.request.Request(BASE + rel, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def udiff(old: str, new: str, rel: str) -> str:
    a = old.replace("\r\n", "\n").splitlines(keepends=True)
    b = new.replace("\r\n", "\n").splitlines(keepends=True)
    if not old.strip():
        a = []
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}"))


def _load_gen():
    gen = ROOT / "scripts" / "gen_ai_patches.py"
    spec = importlib.util.spec_from_file_location("gen_ai_patches", gen)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load scripts/gen_ai_patches.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmake_after_0005(upstream: str) -> str:
    """Reconstruct CMakeLists.txt as it looks after 0003 / 0004 / 0005."""
    marker = "    settings/settings_experimental.h\n"
    if marker not in upstream:
        raise SystemExit("cmake: settings_experimental marker missing")
    return upstream.replace(
        marker,
        marker
        + "    settings/settings_noads.cpp\n"
        + "    settings/settings_noads.h\n"
        + "    noads/noads_ai_options.cpp\n"
        + "    noads/noads_ai_options.h\n"
        + "    lang/translate_llm_provider.cpp\n"
        + "    lang/translate_llm_provider.h\n"
        + "    api/api_custom_transcribe.cpp\n"
        + "    api/api_custom_transcribe.h\n",
        1,
    )


def build() -> str:
    gen = _load_gen()
    settings_noads = gen.SETTINGS_CPP
    ai_options = gen.NOADS_AI_CPP

    notifications = fetch(NOTIFICATIONS_REL)
    cmake_after_0005 = _cmake_after_0005(fetch(CMAKE_REL))

    # --- notifications_manager_win.cpp ---
    notifications_p = notifications.replace(
        '#include "platform/win/windows_dlls.h"\n',
        '#include "platform/win/windows_dlls.h"\n' + NOTIFY_INCLUDE,
        1,
    )
    if NOTIFY_INCLUDE not in notifications_p:
        raise SystemExit("notifications: windows_dlls include anchor missing")
    if SOUND_OLD not in notifications_p:
        raise SystemExit("notifications: SkipSoundForCustom body changed")
    notifications_p = notifications_p.replace(SOUND_OLD, SOUND_NEW, 1)
    if TOAST_OLD not in notifications_p:
        raise SystemExit("notifications: SkipToastForCustom body changed")
    notifications_p = notifications_p.replace(TOAST_OLD, TOAST_NEW, 1)

    # --- settings/settings_noads.cpp (post-0003) ---
    ai_include = '#include "noads/noads_ai_options.h"\n'
    if ai_include not in settings_noads:
        raise SystemExit("settings_noads: ai include anchor missing")
    settings_noads_p = settings_noads.replace(
        ai_include, ai_include + NOTIFY_INCLUDE, 1
    )
    ai_section = (
        '\tUi::AddSubsectionTitle(content, rpl::single(u"AI 翻译（OpenAI 兼容）"_q));\n'
    )
    if ai_section not in settings_noads_p:
        raise SystemExit("settings_noads: AI subsection anchor missing")
    settings_noads_p = settings_noads_p.replace(
        ai_section, NOTIFY_SECTION + ai_section, 1
    )

    # --- noads/noads_ai_options.cpp (post-0004): single registration entry ---
    if ai_include not in ai_options:
        raise SystemExit("noads_ai_options: ai include anchor missing")
    ai_options_p = ai_options.replace(ai_include, ai_include + NOTIFY_INCLUDE, 1)
    if REG_ANCHOR not in ai_options_p:
        raise SystemExit("noads_ai_options: RegisterOptions anchor missing")
    ai_options_p = ai_options_p.replace(REG_ANCHOR, REG_ANCHOR + REG_ADDED, 1)

    # --- CMakeLists.txt (post-0005) ---
    ai_cmake_marker = "    noads/noads_ai_options.h\n"
    if ai_cmake_marker not in cmake_after_0005:
        raise SystemExit("cmake: noads_ai_options.h marker missing")
    cmake_p = cmake_after_0005.replace(
        ai_cmake_marker,
        ai_cmake_marker
        + "    noads/noads_notify_options.cpp\n"
        + "    noads/noads_notify_options.h\n",
        1,
    )

    return "".join(
        [
            udiff(cmake_after_0005, cmake_p, CMAKE_REL),
            udiff("", NOTIFY_CPP, NOTIFY_CPP_REL),
            udiff("", NOTIFY_H, NOTIFY_H_REL),
            udiff(notifications, notifications_p, NOTIFICATIONS_REL),
            udiff(settings_noads, settings_noads_p, SETTINGS_NOADS_REL),
            udiff(ai_options, ai_options_p, AI_OPTIONS_REL),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=DEFAULT_TAG)
    args = parser.parse_args()
    tag = args.tag if args.tag.startswith("v") else f"v{tag}"
    global BASE
    BASE = f"https://raw.githubusercontent.com/telegramdesktop/tdesktop/{tag}/"

    PATCHES.mkdir(parents=True, exist_ok=True)
    text = build()
    if not text.strip():
        raise SystemExit("generated empty patch")
    out = PATCHES / "0006-mute-in-fullscreen.patch"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")


if __name__ == "__main__":
    main()