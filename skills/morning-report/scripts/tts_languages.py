#!/usr/bin/env python3
"""Google TTS language support helper for Morning Report audio."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

TTS_LANGUAGES = {
    "af": {"test_text": "Dit is 'n oudiotoets vir die oggendverslag.", "aliases": ["afrikaans"]},
    "am": {"test_text": "ይህ ለጠዋት ሪፖርት የድምፅ ሙከራ ነው።", "aliases": ["amharic"]},
    "ar": {"test_text": "هذا اختبار صوتي لتقرير الصباح.", "aliases": ["arabic"]},
    "bg": {"test_text": "Това е аудио тест за сутрешния доклад.", "aliases": ["bulgarian"]},
    "bn": {"test_text": "এটি সকালের প্রতিবেদনের জন্য একটি অডিও পরীক্ষা।", "aliases": ["bengali"]},
    "bs": {"test_text": "Ovo je audio test za jutarnji izvještaj.", "aliases": ["bosnian"]},
    "ca": {"test_text": "Aquesta és una prova d'àudio per a l'informe del matí.", "aliases": ["catalan"]},
    "cs": {"test_text": "Toto je zvukový test pro ranní zprávu.", "aliases": ["czech"]},
    "cy": {"test_text": "Prawf sain ar gyfer adroddiad y bore yw hwn.", "aliases": ["welsh"]},
    "da": {"test_text": "Dette er en lydtest til morgenrapporten.", "aliases": ["danish"]},
    "de": {"test_text": "Dies ist ein Audiotest für den Morgenbericht.", "aliases": ["german"]},
    "el": {"test_text": "Αυτή είναι μια δοκιμή ήχου για την πρωινή αναφορά.", "aliases": ["greek"]},
    "en": {"test_text": "This is an audio test for the morning report.", "aliases": ["english"]},
    "es": {"test_text": "Esta es una prueba de audio para el informe de la mañana.", "aliases": ["spanish"]},
    "et": {"test_text": "See on hommikuraporti helitest.", "aliases": ["estonian"]},
    "eu": {"test_text": "Hau goizeko txostenaren audio-proba bat da.", "aliases": ["basque"]},
    "fi": {"test_text": "Tämä on aamuraportin äänitesti.", "aliases": ["finnish"]},
    "fr": {"test_text": "Ceci est un test audio pour le rapport du matin.", "aliases": ["french"]},
    "fr-CA": {
        "test_text": "Ceci est un test audio pour le rapport du matin.",
        "aliases": ["canadian french", "french canadian"],
    },
    "gl": {"test_text": "Esta é unha proba de audio para o informe da mañá.", "aliases": ["galician"]},
    "gu": {"test_text": "આ સવારના અહેવાલ માટેની ઑડિયો કસોટી છે.", "aliases": ["gujarati"]},
    "ha": {"test_text": "Wannan gwajin sauti ne don rahoton safe.", "aliases": ["hausa"]},
    "hi": {"test_text": "यह सुबह की रिपोर्ट के लिए एक ऑडियो परीक्षण है।", "aliases": ["hindi"]},
    "hr": {"test_text": "Ovo je audio test za jutarnje izvješće.", "aliases": ["croatian"]},
    "hu": {"test_text": "Ez egy hangteszt a reggeli jelentéshez.", "aliases": ["hungarian"]},
    "id": {"test_text": "Ini adalah tes audio untuk laporan pagi.", "aliases": ["indonesian"]},
    "is": {"test_text": "Þetta er hljóðpróf fyrir morgunskýrsluna.", "aliases": ["icelandic"]},
    "it": {"test_text": "Questo è un test audio per il rapporto del mattino.", "aliases": ["italian"]},
    "iw": {"test_text": "זוהי בדיקת שמע לדוח הבוקר.", "aliases": ["hebrew", "he"]},
    "ja": {"test_text": "これは朝のレポート用の音声テストです。", "aliases": ["japanese"]},
    "jw": {"test_text": "Iki tes audio kanggo laporan esuk.", "aliases": ["javanese"]},
    "km": {"test_text": "នេះគឺជាការធ្វើតេស្តសំឡេងសម្រាប់របាយការណ៍ពេលព្រឹក។", "aliases": ["khmer"]},
    "kn": {"test_text": "ಇದು ಬೆಳಗಿನ ವರದಿಗಾಗಿ ಧ್ವನಿ ಪರೀಕ್ಷೆಯಾಗಿದೆ.", "aliases": ["kannada"]},
    "ko": {"test_text": "이것은 아침 보고서용 오디오 테스트입니다.", "aliases": ["korean"]},
    "la": {"test_text": "Hoc est experimentum soni relationis matutinae.", "aliases": ["latin"]},
    "lt": {"test_text": "Tai yra rytinės ataskaitos garso testas.", "aliases": ["lithuanian"]},
    "lv": {"test_text": "Šis ir rīta ziņojuma audio tests.", "aliases": ["latvian"]},
    "ml": {"test_text": "ഇത് പ്രഭാത റിപ്പോർട്ടിനുള്ള ഓഡിയോ പരിശോധനയാണ്.", "aliases": ["malayalam"]},
    "mr": {"test_text": "ही सकाळच्या अहवालासाठीची ऑडिओ चाचणी आहे.", "aliases": ["marathi"]},
    "ms": {"test_text": "Ini ialah ujian audio untuk laporan pagi.", "aliases": ["malay"]},
    "my": {"test_text": "ဤသည်မှာ နံနက်ခင်းအစီရင်ခံစာအတွက် အသံစမ်းသပ်မှုဖြစ်သည်။", "aliases": ["burmese", "myanmar"]},
    "ne": {"test_text": "यो बिहानको प्रतिवेदनका लागि अडियो परीक्षण हो।", "aliases": ["nepali"]},
    "nl": {"test_text": "Dit is een audiotest voor het ochtendrapport.", "aliases": ["dutch"]},
    "no": {"test_text": "Dette er en lydtest for morgenrapporten.", "aliases": ["norwegian"]},
    "pa": {"test_text": "ਇਹ ਸਵੇਰ ਦੀ ਰਿਪੋਰਟ ਲਈ ਆਡੀਓ ਟੈਸਟ ਹੈ।", "aliases": ["punjabi"]},
    "pl": {"test_text": "To jest test audio dla porannego raportu.", "aliases": ["polish"]},
    "pt": {"test_text": "Este é um teste de áudio para o relatório da manhã.", "aliases": ["portuguese"]},
    "pt-PT": {
        "test_text": "Este é um teste de áudio para o relatório da manhã.",
        "aliases": ["european portuguese", "portuguese portugal"],
    },
    "ro": {"test_text": "Acesta este un test audio pentru raportul de dimineață.", "aliases": ["romanian"]},
    "ru": {"test_text": "Это аудиотест для утреннего отчёта.", "aliases": ["russian"]},
    "si": {"test_text": "මෙය උදෑසන වාර්තාව සඳහා ශ්‍රව්‍ය පරීක්ෂණයකි.", "aliases": ["sinhala", "sinhalese"]},
    "sk": {"test_text": "Toto je zvukový test pre rannú správu.", "aliases": ["slovak"]},
    "sq": {"test_text": "Ky është një test audio për raportin e mëngjesit.", "aliases": ["albanian"]},
    "sr": {"test_text": "Ово је аудио тест за јутарњи извештај.", "aliases": ["serbian"]},
    "su": {"test_text": "Ieu tés audio pikeun laporan isuk.", "aliases": ["sundanese"]},
    "sv": {"test_text": "Detta är ett ljudtest för morgonrapporten.", "aliases": ["swedish"]},
    "sw": {"test_text": "Hili ni jaribio la sauti kwa ripoti ya asubuhi.", "aliases": ["swahili"]},
    "ta": {"test_text": "இது காலை அறிக்கைக்கான ஒலி சோதனை.", "aliases": ["tamil"]},
    "te": {"test_text": "ఇది ఉదయం నివేదిక కోసం ఆడియో పరీక్ష.", "aliases": ["telugu"]},
    "th": {"test_text": "นี่คือการทดสอบเสียงสำหรับรายงานช่วงเช้า", "aliases": ["thai"]},
    "tl": {"test_text": "Ito ay isang audio test para sa ulat sa umaga.", "aliases": ["tagalog", "filipino"]},
    "tr": {"test_text": "Bu, sabah raporu için bir ses testidir.", "aliases": ["turkish"]},
    "uk": {"test_text": "Це аудіотест для ранкового звіту.", "aliases": ["ukrainian"]},
    "ur": {"test_text": "یہ صبح کی رپورٹ کے لیے ایک آڈیو ٹیسٹ ہے۔", "aliases": ["urdu"]},
    "vi": {"test_text": "Đây là bài kiểm tra âm thanh cho báo cáo buổi sáng.", "aliases": ["vietnamese"]},
    "yue": {"test_text": "呢個係晨報音訊測試。", "aliases": ["cantonese"]},
    "zh-CN": {
        "test_text": "这是晨报音频测试。",
        "aliases": ["chinese", "mandarin", "simplified chinese", "zh"],
    },
    "zh-TW": {
        "test_text": "這是晨報音訊測試。",
        "aliases": ["traditional chinese", "taiwan chinese"],
    },
}

TTS_TEST_TEXTS = {code: data["test_text"] for code, data in TTS_LANGUAGES.items()}
LANGUAGE_ALIASES = {
    alias.lower(): code
    for code, data in TTS_LANGUAGES.items()
    for alias in data.get("aliases", [])
}


def normalize_language_key(value: str) -> str:
    return " ".join(value.strip().replace("_", "-").split())


def resolve_tts_language(value: str | None) -> dict[str, Any]:
    requested = (value or "").strip()
    if not requested:
        return {
            "ok": False,
            "status": "missing_language",
            "requested_lang": requested,
            "lang": None,
            "test_text": None,
        }

    clean = normalize_language_key(requested)
    direct = next((code for code in TTS_TEST_TEXTS if code.lower() == clean.lower()), None)
    lang = direct or LANGUAGE_ALIASES.get(clean.lower())
    if not lang or lang not in TTS_TEST_TEXTS:
        return {
            "ok": False,
            "status": "unsupported_language",
            "requested_lang": requested,
            "lang": None,
            "test_text": None,
        }

    return {
        "ok": True,
        "status": "supported_language",
        "requested_lang": requested,
        "lang": lang,
        "test_text": TTS_TEST_TEXTS[lang],
    }


def google_tts_url(lang: str, text: str) -> str:
    params = urllib.parse.urlencode(
        {
            "ie": "UTF-8",
            "client": "tw-ob",
            "tl": lang,
            "q": text,
        }
    )
    return f"{GOOGLE_TTS_URL}?{params}"


def check_google_tts_language(language: str | None, timeout: int = 10) -> dict[str, Any]:
    resolved = resolve_tts_language(language)
    result: dict[str, Any] = {
        "checked": True,
        "ok": False,
        **resolved,
    }
    if not resolved["ok"]:
        return result

    request = urllib.request.Request(
        google_tts_url(str(resolved["lang"]), str(resolved["test_text"])),
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(512)
        result["ok"] = len(data) > 128
        result["bytes_sampled"] = len(data)
        result["status"] = "supported" if result["ok"] else "empty_or_short_audio"
    except urllib.error.HTTPError as exc:
        result["status"] = "request_failed"
        result["error"] = f"HTTP {exc.code}"
    except Exception as exc:
        result["status"] = "request_failed"
        result["error"] = str(exc)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Google TTS language support")
    parser.add_argument("--language", required=True)
    parser.add_argument("--check", action="store_true", help="Make a live Google TTS probe")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--compact", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = (
        check_google_tts_language(args.language, args.timeout)
        if args.check
        else {"checked": False, **resolve_tts_language(args.language)}
    )
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
