#!/usr/bin/env python3
"""Generate LLM translate + custom STT patches against upstream tdesktop tag."""

from __future__ import annotations

import argparse
import difflib
import urllib.request
from pathlib import Path

DEFAULT_TAG = "v7.0.4"
UA = {"User-Agent": "tdesktop-noads"}
ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches"
BASE = ""


def fetch(rel: str) -> str:
    req = urllib.request.Request(BASE + rel, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def udiff(old: str, new: str, rel: str) -> str:
    a = old.replace("\r\n", "\n").splitlines(keepends=True)
    b = new.replace("\r\n", "\n").splitlines(keepends=True)
    if not old:
        a = []
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    return "".join(
        difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}")
    )


# ---------------------------------------------------------------------------
# Shared option helpers (header-only style constants used by multiple files)
# ---------------------------------------------------------------------------

NOADS_AI_H = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#pragma once

#include "base/options.h"

#include <QtCore/QUrl>

namespace NoAds {
namespace Ai {

inline constexpr auto kEnableTranslate = "noads-ai-translate";
inline constexpr auto kBaseUrl = "noads-ai-base-url";
inline constexpr auto kApiKey = "noads-ai-api-key";
inline constexpr auto kModel = "noads-ai-model";
inline constexpr auto kSystemPrompt = "noads-ai-system-prompt";

inline constexpr auto kEnableStt = "noads-stt-enable";
inline constexpr auto kSttBaseUrl = "noads-stt-base-url";
inline constexpr auto kSttApiKey = "noads-stt-api-key";
inline constexpr auto kSttModel = "noads-stt-model";

[[nodiscard]] inline QString DefaultBaseUrl() {
	return u"https://api.openai.com/v1"_q;
}

[[nodiscard]] inline QString DefaultTranslateModel() {
	return u"gpt-4o-mini"_q;
}

[[nodiscard]] inline QString DefaultSttModel() {
	return u"whisper-1"_q;
}

[[nodiscard]] inline QString DefaultSystemPrompt() {
	return u"You are a professional translator. Translate the user message into the target language. Preserve meaning, tone, and formatting (markdown/emoji) when possible. Output ONLY the translation, with no explanations."_q;
}

[[nodiscard]] inline bool TranslateEnabled() {
	return base::options::lookup<bool>(kEnableTranslate).value();
}

[[nodiscard]] inline bool SttEnabled() {
	return base::options::lookup<bool>(kEnableStt).value();
}

[[nodiscard]] inline QString TranslateBaseUrl() {
	auto v = base::options::lookup<QString>(kBaseUrl).value().trimmed();
	while (v.endsWith('/')) {
		v.chop(1);
	}
	return v.isEmpty() ? DefaultBaseUrl() : v;
}

[[nodiscard]] inline QString TranslateApiKey() {
	return base::options::lookup<QString>(kApiKey).value().trimmed();
}

[[nodiscard]] inline QString TranslateModel() {
	const auto v = base::options::lookup<QString>(kModel).value().trimmed();
	return v.isEmpty() ? DefaultTranslateModel() : v;
}

[[nodiscard]] inline QString SystemPrompt() {
	const auto v = base::options::lookup<QString>(kSystemPrompt).value().trimmed();
	return v.isEmpty() ? DefaultSystemPrompt() : v;
}

[[nodiscard]] inline QString SttBaseUrl() {
	auto v = base::options::lookup<QString>(kSttBaseUrl).value().trimmed();
	if (v.isEmpty()) {
		return TranslateBaseUrl();
	}
	while (v.endsWith('/')) {
		v.chop(1);
	}
	return v;
}

[[nodiscard]] inline QString SttApiKey() {
	const auto v = base::options::lookup<QString>(kSttApiKey).value().trimmed();
	return v.isEmpty() ? TranslateApiKey() : v;
}

[[nodiscard]] inline QString SttModel() {
	const auto v = base::options::lookup<QString>(kSttModel).value().trimmed();
	return v.isEmpty() ? DefaultSttModel() : v;
}

[[nodiscard]] inline bool EndpointAllowed(const QString &base) {
	const auto url = QUrl(base);
	if (!url.isValid() || url.host().isEmpty()) {
		return false;
	}
	if (url.scheme().compare(u"https"_q, Qt::CaseInsensitive) == 0) {
		return true;
	}
	if (url.scheme().compare(u"http"_q, Qt::CaseInsensitive) != 0) {
		return false;
	}
	const auto host = url.host().toLower();
	return host == u"localhost"_q
		|| host == u"127.0.0.1"_q
		|| host == u"::1"_q;
}

[[nodiscard]] inline bool TranslateReady() {
	return TranslateEnabled()
		&& !TranslateApiKey().isEmpty()
		&& EndpointAllowed(TranslateBaseUrl())
		&& !TranslateModel().isEmpty();
}

[[nodiscard]] inline bool SttReady() {
	return SttEnabled()
		&& !SttApiKey().isEmpty()
		&& EndpointAllowed(SttBaseUrl())
		&& !SttModel().isEmpty();
}

// Ensure options are registered (call from any TU that needs them).
void RegisterOptions();

} // namespace Ai
} // namespace NoAds
'''

NOADS_AI_CPP = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#include "noads/noads_ai_options.h"

namespace NoAds {
namespace Ai {
namespace {

base::options::toggle OptionEnableTranslate({
	.id = kEnableTranslate,
	.name = "启用 AI 翻译",
	.description = "使用 OpenAI 兼容接口翻译（覆盖官方/URL/系统翻译）。需填写 API Key。",
	.defaultValue = false,
});

base::options::option<QString> OptionBaseUrl({
	.id = kBaseUrl,
	.name = "AI Base URL",
	.description = "OpenAI 兼容 API 根地址，例如 https://api.openai.com/v1",
	.defaultValue = DefaultBaseUrl(),
});

base::options::option<QString> OptionApiKey({
	.id = kApiKey,
	.name = "AI API Key",
	.description = "Bearer Token。仅保存在本机实验选项配置中。",
	.defaultValue = QString(),
});

base::options::option<QString> OptionModel({
	.id = kModel,
	.name = "AI 翻译模型",
	.description = "chat/completions 使用的模型名。",
	.defaultValue = DefaultTranslateModel(),
});

base::options::option<QString> OptionSystemPrompt({
	.id = kSystemPrompt,
	.name = "AI 翻译系统提示词",
	.description = "可自定义翻译风格；留空使用默认。",
	.defaultValue = DefaultSystemPrompt(),
});

base::options::toggle OptionEnableStt({
	.id = kEnableStt,
	.name = "启用自定义语音转写",
	.description = "使用 OpenAI 兼容 /audio/transcriptions。未配置时回退官方转写。",
	.defaultValue = false,
});

base::options::option<QString> OptionSttBaseUrl({
	.id = kSttBaseUrl,
	.name = "STT Base URL",
	.description = "可留空，默认复用 AI Base URL。",
	.defaultValue = QString(),
});

base::options::option<QString> OptionSttApiKey({
	.id = kSttApiKey,
	.name = "STT API Key",
	.description = "可留空，默认复用 AI API Key。",
	.defaultValue = QString(),
});

base::options::option<QString> OptionSttModel({
	.id = kSttModel,
	.name = "STT 模型",
	.description = "例如 whisper-1 或兼容模型名。",
	.defaultValue = DefaultSttModel(),
});

} // namespace

void RegisterOptions() {
	// ODR-use options so they are constructed.
	(void)OptionEnableTranslate.value();
	(void)OptionBaseUrl.value();
	(void)OptionApiKey.value();
	(void)OptionModel.value();
	(void)OptionSystemPrompt.value();
	(void)OptionEnableStt.value();
	(void)OptionSttBaseUrl.value();
	(void)OptionSttApiKey.value();
	(void)OptionSttModel.value();
}

} // namespace Ai
} // namespace NoAds
'''

# ---------------------------------------------------------------------------
# LLM Translate provider
# ---------------------------------------------------------------------------

LLM_H = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#pragma once

#include "translate_provider.h"

namespace Ui {

[[nodiscard]] std::unique_ptr<TranslateProvider> CreateLlmTranslateProvider(
	std::unique_ptr<TranslateProvider> fallback);

} // namespace Ui
'''

# Final provider implementation used by the generated patch.
LLM_CPP = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#include "lang/translate_llm_provider.h"

#include "noads/noads_ai_options.h"

#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonParseError>
#include <QtCore/QTimer>
#include <QtCore/QUrl>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Ui {
namespace {

class LlmTranslateProvider final : public TranslateProvider {
public:
	explicit LlmTranslateProvider(
			std::unique_ptr<TranslateProvider> fallback)
	: _fallback(std::move(fallback)) {
		NoAds::Ai::RegisterOptions();
	}

	[[nodiscard]] bool supportsMessageId() const override {
		return NoAds::Ai::TranslateReady()
			? false
			: _fallback->supportsMessageId();
	}

	void request(
			TranslateProviderRequest request,
			LanguageId to,
			Fn<void(TranslateProviderResult)> done) override {
		if (!NoAds::Ai::TranslateReady()) {
			_fallback->request(
				std::move(request),
				to,
				std::move(done));
			return;
		}
		if (request.text.text.trimmed().isEmpty()) {
			done({ .error = TranslateProviderError::Unknown });
			return;
		}

		const auto base = NoAds::Ai::TranslateBaseUrl();
		const auto key = NoAds::Ai::TranslateApiKey();
		const auto model = NoAds::Ai::TranslateModel();
		const auto toCode = to.twoLetterCode();
		auto system = NoAds::Ai::SystemPrompt();
		if (!toCode.isEmpty()) {
			system += u"\nTarget language code: "_q + toCode + u"."_q;
		}

		auto messages = QJsonArray();
		messages.append(QJsonObject{
			{ u"role"_q, u"system"_q },
			{ u"content"_q, system },
		});
		messages.append(QJsonObject{
			{ u"role"_q, u"user"_q },
			{ u"content"_q, request.text.text },
		});
		const auto body = QJsonDocument(QJsonObject{
			{ u"model"_q, model },
			{ u"temperature"_q, 0.2 },
			{ u"messages"_q, messages },
		}).toJson(QJsonDocument::Compact);

		auto net = QNetworkRequest(QUrl(base + u"/chat/completions"_q));
		net.setHeader(
			QNetworkRequest::ContentTypeHeader,
			u"application/json"_q);
		net.setRawHeader("Authorization", ("Bearer " + key).toUtf8());

		const auto reply = _network.post(net, body);
		QTimer::singleShot(60 * 1000, reply, [=] {
			if (reply->isRunning()) {
				reply->abort();
			}
		});
		QObject::connect(reply, &QNetworkReply::finished, reply, [=] {
			auto finish = [&](TranslateProviderResult result) {
				done(std::move(result));
				reply->deleteLater();
			};
			if (reply->error() != QNetworkReply::NoError) {
				finish({ .error = TranslateProviderError::Unknown });
				return;
			}
			auto parseError = QJsonParseError();
			const auto doc = QJsonDocument::fromJson(
				reply->readAll(),
				&parseError);
			if (parseError.error != QJsonParseError::NoError
				|| !doc.isObject()) {
				finish({ .error = TranslateProviderError::Unknown });
				return;
			}
			const auto choices = doc.object().value(u"choices"_q).toArray();
			if (choices.isEmpty()) {
				finish({ .error = TranslateProviderError::Unknown });
				return;
			}
			const auto msg = choices.at(0).toObject()
				.value(u"message"_q).toObject();
			auto content = msg.value(u"content"_q).toString().trimmed();
			if (content.isEmpty() && msg.value(u"content"_q).isArray()) {
				for (const auto &part : msg.value(u"content"_q).toArray()) {
					if (part.isString()) {
						content += part.toString();
					} else if (part.isObject()) {
						content += part.toObject().value(u"text"_q).toString();
					}
				}
				content = content.trimmed();
			}
			if (content.isEmpty()) {
				finish({ .error = TranslateProviderError::Unknown });
				return;
			}
			finish({ .text = TextWithEntities{ content } });
		});
	}

private:
	std::unique_ptr<TranslateProvider> _fallback;
	QNetworkAccessManager _network;

};

} // namespace

std::unique_ptr<TranslateProvider> CreateLlmTranslateProvider(
		std::unique_ptr<TranslateProvider> fallback) {
	return std::make_unique<LlmTranslateProvider>(std::move(fallback));
}

} // namespace Ui
'''

# ---------------------------------------------------------------------------
# Custom STT
# ---------------------------------------------------------------------------

STT_H = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#pragma once

class HistoryItem;

namespace Api {

// Returns true if custom STT started (caller should not use official API).
bool TryCustomTranscribe(
	not_null<HistoryItem*> item,
	Fn<void(QString text, bool failed)> done);

[[nodiscard]] bool CustomTranscribeReady();

} // namespace Api
'''

# Final STT implementation used by the generated patch.
STT_CPP = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#include "api/api_custom_transcribe.h"

#include "base/timer.h"
#include "base/weak_ptr.h"
#include "data/data_document.h"
#include "data/data_document_media.h"
#include "data/data_file_origin.h"
#include "data/data_session.h"
#include "history/history_item.h"
#include "main/main_session.h"
#include "noads/noads_ai_options.h"

#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonParseError>
#include <QtCore/QTimer>
#include <QtCore/QUrl>
#include <QtNetwork/QHttpMultiPart>
#include <QtNetwork/QHttpPart>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Api {
namespace {

QNetworkAccessManager &Network() {
	static QNetworkAccessManager instance;
	return instance;
}

[[nodiscard]] QByteArray ReadAudioBytes(
		not_null<DocumentData*> document,
		const std::shared_ptr<Data::DocumentMedia> &media) {
	if (media) {
		const auto bytes = media->bytes();
		if (!bytes.isEmpty()) {
			return bytes;
		}
	}
	const auto path = document->filepath(true);
	if (path.isEmpty()) {
		return {};
	}
	auto f = QFile(path);
	if (!f.open(QIODevice::ReadOnly)) {
		return {};
	}
	return f.readAll();
}

[[nodiscard]] QString GuessFilename(not_null<DocumentData*> document) {
	auto name = document->filename();
	if (!name.isEmpty()) {
		return name;
	}
	const auto path = document->filepath(true);
	if (!path.isEmpty()) {
		return QFileInfo(path).fileName();
	}
	if (document->isVideoMessage()) {
		return u"video-note.mp4"_q;
	} else if (document->isVoiceMessage()) {
		return u"voice.ogg"_q;
	}
	return u"audio.bin"_q;
}

[[nodiscard]] QString GuessMime(
		not_null<DocumentData*> document,
		const QString &filename) {
	const auto declared = document->mimeString().trimmed();
	if (!declared.isEmpty()) {
		return declared;
	}
	const auto lower = filename.toLower();
	if (lower.endsWith(u".ogg"_q) || lower.endsWith(u".opus"_q)) {
		return u"audio/ogg"_q;
	} else if (lower.endsWith(u".mp3"_q)) {
		return u"audio/mpeg"_q;
	} else if (lower.endsWith(u".wav"_q)) {
		return u"audio/wav"_q;
	} else if (lower.endsWith(u".m4a"_q) || lower.endsWith(u".mp4"_q)) {
		return u"audio/mp4"_q;
	} else if (lower.endsWith(u".webm"_q)) {
		return u"audio/webm"_q;
	}
	return u"application/octet-stream"_q;
}

void UploadBytes(
		QByteArray bytes,
		QString filename,
		QString mime,
		Fn<void(QString text, bool failed)> done) {
	constexpr auto kMaxUploadBytes = 24 * 1024 * 1024;
	if (bytes.isEmpty() || bytes.size() > kMaxUploadBytes) {
		done({}, true);
		return;
	}
	const auto base = NoAds::Ai::SttBaseUrl();
	const auto key = NoAds::Ai::SttApiKey();
	const auto model = NoAds::Ai::SttModel();

	const auto multi = new QHttpMultiPart(QHttpMultiPart::FormDataType);
	{
		QHttpPart modelPart;
		modelPart.setHeader(
			QNetworkRequest::ContentDispositionHeader,
			QVariant(u"form-data; name=\"model\""_q));
		modelPart.setBody(model.toUtf8());
		multi->append(modelPart);
	}
	{
		QHttpPart filePart;
		filePart.setHeader(
			QNetworkRequest::ContentDispositionHeader,
			QVariant(
				u"form-data; name=\"file\"; filename=\"%1\""_q.arg(
					filename)));
		filePart.setHeader(
			QNetworkRequest::ContentTypeHeader,
			QVariant(mime));
		filePart.setBody(bytes);
		multi->append(filePart);
	}

	auto req = QNetworkRequest(QUrl(base + u"/audio/transcriptions"_q));
	req.setRawHeader("Authorization", ("Bearer " + key).toUtf8());
	const auto reply = Network().post(req, multi);
	multi->setParent(reply);
	QTimer::singleShot(60 * 1000, reply, [=] {
		if (reply->isRunning()) {
			reply->abort();
		}
	});

	QObject::connect(reply, &QNetworkReply::finished, reply, [=] {
		QString text;
		bool failed = true;
		if (reply->error() == QNetworkReply::NoError) {
			const auto body = reply->readAll();
			auto err = QJsonParseError();
			const auto doc = QJsonDocument::fromJson(body, &err);
			if (err.error == QJsonParseError::NoError && doc.isObject()) {
				text = doc.object().value(u"text"_q).toString().trimmed();
				failed = text.isEmpty();
			} else {
				text = QString::fromUtf8(body).trimmed();
				failed = text.isEmpty();
			}
		}
		done(text, failed);
		reply->deleteLater();
	});
}

void WaitLoadedThenUpload(
		base::weak_ptr<Main::Session> session,
		DocumentId documentId,
		std::shared_ptr<Data::DocumentMedia> media,
		Fn<void(QString, bool)> done) {
	struct State {
		std::shared_ptr<State> keepAlive;
		std::shared_ptr<Data::DocumentMedia> media;
		base::weak_ptr<Main::Session> session;
		DocumentId documentId = 0;
		base::Timer timer;
		int tries = 0;
		Fn<void(QString, bool)> done;
	};
	const auto state = std::make_shared<State>();
	state->keepAlive = state;
	state->media = std::move(media);
	state->session = std::move(session);
	state->documentId = documentId;
	state->done = std::move(done);

	state->timer.setCallback([weak = std::weak_ptr<State>(state)] {
		const auto state = weak.lock();
		if (!state) {
			return;
		}
		const auto session = state->session.get();
		if (!session) {
			state->timer.cancel();
			auto done = std::move(state->done);
			state->keepAlive.reset();
			done({}, true);
			return;
		}
		const auto document = session->data().document(state->documentId);
		const auto bytes = ReadAudioBytes(document, state->media);
		if (!bytes.isEmpty()) {
			state->timer.cancel();
			auto done = std::move(state->done);
			state->keepAlive.reset();
			const auto filename = GuessFilename(document);
			UploadBytes(
				bytes,
				filename,
				GuessMime(document, filename),
				std::move(done));
			return;
		}
		++state->tries;
		if (state->tries > 200) { // ~20s
			state->timer.cancel();
			auto done = std::move(state->done);
			state->keepAlive.reset();
			done({}, true);
			return;
		}
		state->timer.callOnce(100);
	});
	state->timer.callOnce(100);
}

void StartWithDocument(
		not_null<HistoryItem*> item,
		not_null<DocumentData*> document,
		Fn<void(QString, bool)> done) {
	constexpr auto kMaxUploadBytes = 24 * 1024 * 1024;
	if (document->size > kMaxUploadBytes) {
		done({}, true);
		return;
	}
	auto media = document->createMediaView();
	const auto bytes = ReadAudioBytes(document, media);
	if (!bytes.isEmpty()) {
		const auto filename = GuessFilename(document);
		UploadBytes(
			bytes,
			filename,
			GuessMime(document, filename),
			std::move(done));
		return;
	}
	document->save(Data::FileOrigin(item->fullId()), QString());
	WaitLoadedThenUpload(
		base::make_weak(&document->session()),
		document->id,
		std::move(media),
		std::move(done));
}

} // namespace

bool CustomTranscribeReady() {
	NoAds::Ai::RegisterOptions();
	return NoAds::Ai::SttReady();
}

bool TryCustomTranscribe(
		not_null<HistoryItem*> item,
		Fn<void(QString text, bool failed)> done) {
	NoAds::Ai::RegisterOptions();
	if (!NoAds::Ai::SttReady()) {
		return false;
	}
	const auto media = item->media();
	const auto document = media ? media->document() : nullptr;
	if (!document) {
		return false;
	}
	if (!document->isVoiceMessage()
		&& !document->isVideoMessage()
		&& !document->isAudioFile()) {
		return false;
	}
	StartWithDocument(item, document, std::move(done));
	return true;
}

} // namespace Api
'''

# ---------------------------------------------------------------------------
# Settings page (full replace of 0003 content)
# ---------------------------------------------------------------------------

SETTINGS_H = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#pragma once

#include "settings/settings_common_session.h"

namespace Settings {

class NoAds : public Section<NoAds> {
public:
	NoAds(
		QWidget *parent,
		not_null<Window::SessionController*> controller);

	[[nodiscard]] rpl::producer<QString> title() override;

private:
	void setupContent();

};

[[nodiscard]] Type NoAdsId();

} // namespace Settings
'''

SETTINGS_CPP = r'''/*
This file is part of tdesktop-noads patches for Telegram Desktop.
*/
#include "settings/settings_noads.h"

#include "base/options.h"
#include "noads/noads_ai_options.h"
#include "settings/settings_common.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/widgets/labels.h"
#include "ui/wrap/vertical_layout.h"
#include "window/window_session_controller.h"

namespace Settings {
namespace {

void AddToggle(
		not_null<Ui::VerticalLayout*> container,
		const char *optionId) {
	auto &option = base::options::lookup<bool>(optionId);
	const auto name = option.name().isEmpty()
		? QString::fromUtf8(optionId)
		: option.name();
	const auto description = option.description();

	Ui::AddSkip(container, st::settingsCheckboxesSkip);
	const auto toggles = container->lifetime().make_state<
		rpl::event_stream<bool>>();
	const auto button = container->add(object_ptr<Button>(
		container,
		rpl::single(name),
		st::settingsButtonNoIcon
	))->toggleOn(toggles->events_starting_with(option.value()));

	button->toggledChanges(
	) | rpl::on_next([=, &option](bool toggled) {
		if (option.value() != toggled) {
			option.set(toggled);
		}
	}, button->lifetime());

	if (!description.isEmpty()) {
		Ui::AddSkip(container, st::settingsCheckboxesSkip);
		Ui::AddDividerText(container, rpl::single(description));
	}
}

// Use InputField for all string options; it is a Ui::RpWidget and can be added
// directly to VerticalLayout.
void AddStringOption(
		not_null<Ui::VerticalLayout*> container,
		const char *optionId) {
	auto &option = base::options::lookup<QString>(optionId);
	const auto title = option.name().isEmpty()
		? QString::fromUtf8(optionId)
		: option.name();

	Ui::AddSkip(container);
	container->add(
		object_ptr<Ui::FlatLabel>(
			container,
			rpl::single(title),
			st::boxLabel),
		st::defaultBoxDividerLabelPadding);

	const auto field = container->add(
		object_ptr<Ui::InputField>(
			container,
			st::defaultInputField,
			rpl::single(title),
			option.value()),
		st::defaultBoxDividerLabelPadding);
	field->submits(
	) | rpl::on_next([=, &option] {
		option.set(field->getLastText().trimmed());
	}, field->lifetime());
	field->changes(
	) | rpl::on_next([=, &option] {
		option.set(field->getLastText());
	}, field->lifetime());

	if (!option.description().isEmpty()) {
		Ui::AddDividerText(container, rpl::single(option.description()));
	}
}

} // namespace

NoAds::NoAds(
	QWidget *parent,
	not_null<Window::SessionController*> controller)
: Section(parent, controller) {
	::NoAds::Ai::RegisterOptions();
	setupContent();
}

rpl::producer<QString> NoAds::title() {
	return rpl::single(u"去广告 / AI / 语音"_q);
}

void NoAds::setupContent() {
	const auto content = Ui::CreateChild<Ui::VerticalLayout>(this);
	Ui::AddSkip(content);
	Ui::AddSubsectionTitle(content, rpl::single(u"基础"_q));
	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			rpl::single(
				u"以下均为本客户端本地设置。API Key 只存在本机，不会上传到本仓库。"_q),
			st::boxLabel),
		st::defaultBoxDividerLabelPadding);

	AddToggle(content, "noads-disable-ads");
	AddToggle(content, "noads-local-premium");

	Ui::AddSkip(content);
	Ui::AddDivider(content);
	Ui::AddSkip(content);
	Ui::AddSubsectionTitle(content, rpl::single(u"AI 翻译（OpenAI 兼容）"_q));
	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			rpl::single(
				u"开启后，单条翻译与自动翻译均走 chat/completions。需可访问的 Base URL 与 API Key。"_q),
			st::boxLabel),
		st::defaultBoxDividerLabelPadding);

	AddToggle(content, "noads-ai-translate");
	AddStringOption(content, "noads-ai-base-url");
	AddStringOption(content, "noads-ai-api-key");
	AddStringOption(content, "noads-ai-model");
	AddStringOption(content, "noads-ai-system-prompt");

	Ui::AddSkip(content);
	Ui::AddDivider(content);
	Ui::AddSkip(content);
	Ui::AddSubsectionTitle(content, rpl::single(u"自定义语音转写 STT"_q));
	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			rpl::single(
				u"开启后优先使用 /audio/transcriptions。STT 的 URL/Key/模型可留空以复用上方 AI 配置。失败时可改回关闭使用官方转写。"_q),
			st::boxLabel),
		st::defaultBoxDividerLabelPadding);

	AddToggle(content, "noads-stt-enable");
	AddStringOption(content, "noads-stt-base-url");
	AddStringOption(content, "noads-stt-api-key");
	AddStringOption(content, "noads-stt-model");

	Ui::AddSkip(content);
	Ui::AddDividerText(
		content,
		rpl::single(
			u"非官方构建。请自备 API。AI/STT 产生费用与隐私责任由你自行承担。"_q));

	Ui::ResizeFitChild(this, content);
}

Type NoAdsId() {
	return NoAds::Id();
}

} // namespace Settings
'''

def patch_translate_provider(src: str) -> str:
    if "translate_llm_provider.h" in src:
        return src
    out = src.replace(
        '#include "lang/translate_url_provider.h"\n',
        '#include "lang/translate_url_provider.h"\n'
        '#include "lang/translate_llm_provider.h"\n'
        '#include "noads/noads_ai_options.h"\n',
        1,
    )
    old = """std::unique_ptr<TranslateProvider> CreateTranslateProvider(
		not_null<Main::Session*> session) {
	const auto urlTemplate = OptionTranslateUrlTemplate.value();
	if (!urlTemplate.isEmpty()
		&& urlTemplate.contains(u"%q"_q)) {
		return CreateUrlTranslateProvider(urlTemplate);
	}
	if (Core::App().settings().usePlatformTranslation()
		&& Platform::IsTranslateProviderAvailable()) {
		return Platform::CreateTranslateProvider();
	}
	return CreateMTProtoTranslateProvider(session);
}
"""
    new = """std::unique_ptr<TranslateProvider> CreateTranslateProvider(
		not_null<Main::Session*> session) {
	NoAds::Ai::RegisterOptions();
	auto fallback = std::unique_ptr<TranslateProvider>();
	const auto urlTemplate = OptionTranslateUrlTemplate.value();
	if (!urlTemplate.isEmpty()
		&& urlTemplate.contains(u"%q"_q)) {
		fallback = CreateUrlTranslateProvider(urlTemplate);
	} else if (Core::App().settings().usePlatformTranslation()
		&& Platform::IsTranslateProviderAvailable()) {
		fallback = Platform::CreateTranslateProvider();
	} else {
		fallback = CreateMTProtoTranslateProvider(session);
	}
	return CreateLlmTranslateProvider(std::move(fallback));
}
"""
    if old not in out:
        raise SystemExit("translate_provider factory anchor missing")
    return out.replace(old, new, 1)


def patch_transcribes_header(src: str) -> str:
    out = src
    if '#include "base/weak_ptr.h"' not in out:
        out = out.replace(
            '#include "mtproto/sender.h"\n',
            '#include "mtproto/sender.h"\n#include "base/weak_ptr.h"\n',
            1,
        )
    out = out.replace(
        "class Transcribes final {",
        "class Transcribes final : public base::has_weak_ptr {",
        1,
    )
    out = out.replace(
        "void load(not_null<HistoryItem*> item);",
        "void load(not_null<HistoryItem*> item, bool custom = true);",
        1,
    )
    return out


def patch_transcribes(src: str) -> str:
    if "api_custom_transcribe.h" in src:
        return src
    out = src.replace(
        '#include "spellcheck/spellcheck_types.h"\n',
        '#include "spellcheck/spellcheck_types.h"\n'
        '#include "api/api_custom_transcribe.h"\n',
        1,
    )
    out = out.replace(
        "void Transcribes::load(not_null<HistoryItem*> item) {",
        "void Transcribes::load(\n\t\tnot_null<HistoryItem*> item,\n\t\tbool custom) {",
        1,
    )
    # Insert the custom path immediately before the official request.
    anchor = """	const auto id = item->fullId();
	const auto requestId = _api.request(MTPmessages_TranscribeAudio(
"""
    insert = """	const auto id = item->fullId();
	if (custom && CustomTranscribeReady()) {
		auto &entry = _map.emplace(id).first->second;
		entry.requestId = 1; // non-zero => loading
		entry.shown = true;
		entry.failed = false;
		entry.pending = true;
		entry.result = QString();
		const auto weak = base::make_weak(this);
		const auto ok = TryCustomTranscribe(item, [=](QString text, bool failed) {
			if (!weak) {
				return;
			}
			if (failed || text.isEmpty()) {
				if (const auto current = weak->_session->data().message(id)) {
					weak->load(current, false);
				} else {
					weak->_map.erase(id);
				}
				return;
			}
			auto &entry = weak->_map[id];
			entry.requestId = 0;
			entry.pending = false;
			entry.failed = false;
			entry.result = text;
			if (const auto current = weak->_session->data().message(id)) {
				toggleRound(current, entry);
				weak->_session->data().requestItemResize(current);
			}
		});
		if (ok) {
			return;
		}
		// Unsupported media falls through to the official API.
		entry.requestId = 0;
		entry.pending = false;
	}
	const auto requestId = _api.request(MTPmessages_TranscribeAudio(
"""
    if anchor not in out:
        raise SystemExit("transcribes load anchor missing")
    return out.replace(anchor, insert, 1)


def patch_transcribe_button(src: str) -> str:
    if "api_custom_transcribe.h" in src and "CustomTranscribeReady" in src:
        return src
    out = src
    if '#include "api/api_custom_transcribe.h"' not in out:
        out = out.replace(
            '#include "api/api_transcribes.h"\n',
            '#include "api/api_transcribes.h"\n'
            '#include "api/api_custom_transcribe.h"\n',
            1,
        )
    old = """bool TranscribeButton::hasLock() const {
	const auto session = &_item->history()->session();
	if (session->premium()) {
		return false;
	}
"""
    new = """bool TranscribeButton::hasLock() const {
	const auto session = &_item->history()->session();
	if (session->premium()) {
		return false;
	}
	if (!_summarize && Api::CustomTranscribeReady()) {
		return false;
	}
"""
    if old not in out:
        raise SystemExit("transcribe hasLock anchor missing")
    out = out.replace(old, new, 1)

    # Also allow click path for non-premium when custom STT ready
    old2 = """		if (session->premium()) {
			auto &transcribes = session->api().transcribes();
			return summarize
				? transcribes.toggleSummary(item)
				: transcribes.toggle(item);
		}
		const auto my = context.other.value<ClickHandlerContext>();
		if (hasLock()) {
"""
    new2 = """		if (session->premium()
			|| (!summarize && Api::CustomTranscribeReady())) {
			auto &transcribes = session->api().transcribes();
			return summarize
				? transcribes.toggleSummary(item)
				: transcribes.toggle(item);
		}
		const auto my = context.other.value<ClickHandlerContext>();
		if (hasLock()) {
"""
    if old2 not in out:
        raise SystemExit("transcribe link premium anchor missing")
    return out.replace(old2, new2, 1)


def patch_cmake(src: str) -> str:
    out = src
    if "noads/noads_ai_options.cpp" not in out:
        marker = "    settings/settings_experimental.h\n"
        if "settings/settings_noads.cpp" in out:
            marker = "    settings/settings_noads.h\n"
        add = (
            marker
            + "    noads/noads_ai_options.cpp\n"
            + "    noads/noads_ai_options.h\n"
            + "    lang/translate_llm_provider.cpp\n"
            + "    lang/translate_llm_provider.h\n"
            + "    api/api_custom_transcribe.cpp\n"
            + "    api/api_custom_transcribe.h\n"
        )
        if marker not in out:
            # try experimental only
            marker = "    settings/settings_experimental.h\n"
            add = (
                marker
                + "    settings/settings_noads.cpp\n"
                + "    settings/settings_noads.h\n"
                + "    noads/noads_ai_options.cpp\n"
                + "    noads/noads_ai_options.h\n"
                + "    lang/translate_llm_provider.cpp\n"
                + "    lang/translate_llm_provider.h\n"
                + "    api/api_custom_transcribe.cpp\n"
                + "    api/api_custom_transcribe.h\n"
            )
        if marker not in out:
            raise SystemExit("cmake marker missing")
        # Avoid duplicating settings_noads if already present via 0003
        if "settings/settings_noads.cpp" in out:
            add = (
                "    settings/settings_experimental.h\n"
                if marker.startswith("    settings/settings_experimental")
                else marker
            )
            # insert after settings_noads.h if present
            m2 = "    settings/settings_noads.h\n"
            if m2 in out:
                out = out.replace(
                    m2,
                    m2
                    + "    noads/noads_ai_options.cpp\n"
                    + "    noads/noads_ai_options.h\n"
                    + "    lang/translate_llm_provider.cpp\n"
                    + "    lang/translate_llm_provider.h\n"
                    + "    api/api_custom_transcribe.cpp\n"
                    + "    api/api_custom_transcribe.h\n",
                    1,
                )
            else:
                out = out.replace(marker, add, 1)
        else:
            out = out.replace(marker, add, 1)
    return out


def patch_settings_main(src: str) -> str:
    out = src
    if '#include "settings/settings_noads.h"' not in out:
        out = out.replace(
            '#include "settings/settings_power_saving.h"\n',
            '#include "settings/settings_power_saving.h"\n'
            '#include "settings/settings_noads.h"\n',
            1,
        )
    if "NoAdsId()" not in out:
        anchor = """	builder.addSectionButton({
		.title = tr::lng_settings_advanced(),
		.targetSection = AdvancedId(),
"""
        idx = out.find(anchor)
        if idx < 0:
            raise SystemExit("settings_main advanced missing")
        j = out.find("});", idx) + 3
        btn = """

	builder.addSectionButton({
		.title = rpl::single(u"去广告 / AI / 语音"_q),
		.targetSection = NoAdsId(),
		.icon = { &st::menuIconFave },
		.keywords = {
			u"ads"_q,
			u"premium"_q,
			u"ai"_q,
			u"translate"_q,
			u"stt"_q,
			u"whisper"_q,
			u"翻译"_q,
			u"语音"_q,
		},
	});
"""
        out = out[:j] + btn + out[j:]
    else:
        # update title string if old
        out = out.replace(
            'u"去广告与本地会员"_q',
            'u"去广告 / AI / 语音"_q',
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=DEFAULT_TAG)
    args = parser.parse_args()
    tag = args.tag if args.tag.startswith("v") else f"v{args.tag}"
    global BASE
    BASE = f"https://raw.githubusercontent.com/telegramdesktop/tdesktop/{tag}/"

    PATCHES.mkdir(parents=True, exist_ok=True)

    # Fetch upstream files for hooks.
    tp = fetch("Telegram/SourceFiles/lang/translate_provider.cpp")
    trh = fetch("Telegram/SourceFiles/api/api_transcribes.h")
    tr = fetch("Telegram/SourceFiles/api/api_transcribes.cpp")
    tb = fetch(
        "Telegram/SourceFiles/history/view/history_view_transcribe_button.cpp"
    )
    cmake = fetch("Telegram/CMakeLists.txt")
    smain = fetch(
        "Telegram/SourceFiles/settings/sections/settings_main.cpp"
    )

    # 0004: AI options + LLM translate + cmake entries (partial)
    p4 = []
    p4.append(udiff("", NOADS_AI_H, "Telegram/SourceFiles/noads/noads_ai_options.h"))
    p4.append(udiff("", NOADS_AI_CPP, "Telegram/SourceFiles/noads/noads_ai_options.cpp"))
    p4.append(udiff("", LLM_H, "Telegram/SourceFiles/lang/translate_llm_provider.h"))
    p4.append(udiff("", LLM_CPP, "Telegram/SourceFiles/lang/translate_llm_provider.cpp"))
    p4.append(
        udiff(
            tp,
            patch_translate_provider(tp),
            "Telegram/SourceFiles/lang/translate_provider.cpp",
        )
    )
    # cmake only AI translate files first - STT in 0005
    cmake4 = cmake
    marker = "    settings/settings_experimental.h\n"
    if marker not in cmake4:
        raise SystemExit("cmake experimental missing")
    # 0003 may already add settings_noads - generate against clean upstream
    cmake4_n = cmake4.replace(
        marker,
        marker
        + "    settings/settings_noads.cpp\n"
        + "    settings/settings_noads.h\n"
        + "    noads/noads_ai_options.cpp\n"
        + "    noads/noads_ai_options.h\n"
        + "    lang/translate_llm_provider.cpp\n"
        + "    lang/translate_llm_provider.h\n",
        1,
    )
    # Wait - 0003 already adds settings_noads. So 0004 should only add noads+llm after experimental OR after noads.
    # Patches apply sequentially: after 0003, cmake has settings_noads. Generate 0004 against post-0003 state.
    cmake_after_0003 = cmake.replace(
        marker,
        marker
        + "    settings/settings_noads.cpp\n"
        + "    settings/settings_noads.h\n",
        1,
    )
    cmake4_from = cmake_after_0003
    cmake4_to = cmake_after_0003.replace(
        "    settings/settings_noads.h\n",
        "    settings/settings_noads.h\n"
        "    noads/noads_ai_options.cpp\n"
        "    noads/noads_ai_options.h\n"
        "    lang/translate_llm_provider.cpp\n"
        "    lang/translate_llm_provider.h\n",
        1,
    )
    p4.append(udiff(cmake4_from, cmake4_to, "Telegram/CMakeLists.txt"))
    (PATCHES / "0004-llm-translate.patch").write_text(
        "".join(p4), encoding="utf-8", newline="\n"
    )
    print("wrote 0004-llm-translate.patch")

    # 0005: STT
    p5 = []
    p5.append(udiff("", STT_H, "Telegram/SourceFiles/api/api_custom_transcribe.h"))
    p5.append(udiff("", STT_CPP, "Telegram/SourceFiles/api/api_custom_transcribe.cpp"))
    p5.append(
        udiff(
            trh,
            patch_transcribes_header(trh),
            "Telegram/SourceFiles/api/api_transcribes.h",
        )
    )
    p5.append(
        udiff(
            tr,
            patch_transcribes(tr),
            "Telegram/SourceFiles/api/api_transcribes.cpp",
        )
    )
    p5.append(
        udiff(
            tb,
            patch_transcribe_button(tb),
            "Telegram/SourceFiles/history/view/history_view_transcribe_button.cpp",
        )
    )
    cmake5_from = cmake4_to
    cmake5_to = cmake5_from.replace(
        "    lang/translate_llm_provider.h\n",
        "    lang/translate_llm_provider.h\n"
        "    api/api_custom_transcribe.cpp\n"
        "    api/api_custom_transcribe.h\n",
        1,
    )
    p5.append(udiff(cmake5_from, cmake5_to, "Telegram/CMakeLists.txt"))
    (PATCHES / "0005-custom-stt.patch").write_text(
        "".join(p5), encoding="utf-8", newline="\n"
    )
    print("wrote 0005-custom-stt.patch")

    # 0003 rewrite: settings page with AI fields + main entry
    # Generate against clean upstream (same as old 0003)
    p3 = []
    p3.append(
        udiff("", SETTINGS_H, "Telegram/SourceFiles/settings/settings_noads.h")
    )
    p3.append(
        udiff("", SETTINGS_CPP, "Telegram/SourceFiles/settings/settings_noads.cpp")
    )
    cmake3 = cmake.replace(
        marker,
        marker
        + "    settings/settings_noads.cpp\n"
        + "    settings/settings_noads.h\n",
        1,
    )
    p3.append(udiff(cmake, cmake3, "Telegram/CMakeLists.txt"))
    p3.append(
        udiff(
            smain,
            patch_settings_main(smain),
            "Telegram/SourceFiles/settings/sections/settings_main.cpp",
        )
    )
    (PATCHES / "0003-settings-noads-page.patch").write_text(
        "".join(p3), encoding="utf-8", newline="\n"
    )
    print("rewrote 0003-settings-noads-page.patch")

    print("done")


if __name__ == "__main__":
    main()
