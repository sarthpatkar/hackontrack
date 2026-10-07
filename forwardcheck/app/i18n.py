"""User-facing strings in English, Hindi and Marathi."""
from __future__ import annotations

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}
SUPPORTED = ("en", "hi", "mr")

LABELS = {
    "VERIFIED": {"en": "Verified", "hi": "सत्यापित", "mr": "पडताळले (खरे)"},
    "FALSE": {"en": "False", "hi": "गलत", "mr": "खोटे"},
    "OUTDATED": {"en": "Outdated", "hi": "पुराना", "mr": "कालबाह्य"},
    "PARTLY_SUPPORTED": {"en": "Partly supported", "hi": "आंशिक रूप से सही", "mr": "अंशतः बरोबर"},
    "CANNOT_BE_CONFIRMED": {"en": "Cannot be confirmed", "hi": "पुष्टि नहीं हो सकी", "mr": "पुष्टी करता आली नाही"},
}
EMOJI = {"VERIFIED": "✅", "FALSE": "❌", "OUTDATED": "⏳", "PARTLY_SUPPORTED": "⚠️", "CANNOT_BE_CONFIRMED": "❓"}

STR = {
    "claim": {"en": "Claim", "hi": "दावा", "mr": "दावा"},
    "verdict": {"en": "Verdict", "hi": "निष्कर्ष", "mr": "निकाल"},
    "wrong": {"en": "What's wrong / right", "hi": "क्या गलत / सही है", "mr": "काय चुकीचे / बरोबर आहे"},
    "evidence": {"en": "Evidence", "hi": "सबूत", "mr": "पुरावा"},
    "summary": {"en": "In simple words", "hi": "आसान शब्दों में", "mr": "सोप्या शब्दांत"},
    "checking": {
        "en": "Checking your forward. This can take up to a minute…",
        "hi": "आपका फ़ॉरवर्ड जाँचा जा रहा है। इसमें एक मिनट तक लग सकता है…",
        "mr": "तुमचा फॉरवर्ड तपासत आहे. यासाठी एक मिनिट लागू शकतो…",
    },
    "no_claims": {
        "en": "I couldn't find a factual claim to check in this message.",
        "hi": "इस संदेश में जाँचने लायक कोई तथ्यात्मक दावा नहीं मिला।",
        "mr": "या संदेशात तपासण्यासारखा कोणताही तथ्यात्मक दावा सापडला नाही.",
    },
    "error": {
        "en": "Sorry, I couldn't check this right now. Please try again in a minute.",
        "hi": "क्षमा करें, अभी इसे जाँच नहीं सका। कृपया एक मिनट बाद फिर कोशिश करें।",
        "mr": "क्षमस्व, आत्ता हे तपासता आले नाही. कृपया एका मिनिटाने पुन्हा प्रयत्न करा.",
    },
    "no_evidence": {
        "en": "No reliable source we checked confirms or contradicts this claim, so we can't say whether it is true.",
        "hi": "हमारे देखे गए किसी भरोसेमंद स्रोत ने इस दावे की पुष्टि या खंडन नहीं किया, इसलिए हम नहीं कह सकते कि यह सच है या नहीं।",
        "mr": "आम्ही तपासलेल्या कोणत्याही विश्वासार्ह स्रोताने या दाव्याची पुष्टी किंवा खंडन केलेले नाही, म्हणून हे खरे आहे की नाही हे सांगता येत नाही.",
    },
    "footer": {
        "en": "Reply HINDI, MARATHI or ENGLISH to change language.",
        "hi": "भाषा बदलने के लिए HINDI, MARATHI या ENGLISH लिखें।",
        "mr": "भाषा बदलण्यासाठी HINDI, MARATHI किंवा ENGLISH लिहा.",
    },
    "more_claims": {
        "en": "This message had more claims than I can check at once; I checked the {n} most important.",
        "hi": "इस संदेश में एक साथ जाँचने से ज़्यादा दावे थे; मैंने सबसे ज़रूरी {n} जाँचे।",
        "mr": "या संदेशात एकाच वेळी तपासता येतील त्यापेक्षा जास्त दावे होते; मी सर्वात महत्त्वाचे {n} तपासले.",
    },
    "help": {
        "en": (
            "Hi! I check forwarded messages. Send me a message, screenshot, voice note, PDF or link, "
            "and I'll tell you if each claim is Verified, False, Outdated, Partly supported or Cannot be confirmed, "
            "with the evidence.\n\nReply HINDI, MARATHI or ENGLISH to choose the reply language."
        ),
        "hi": (
            "नमस्ते! मैं फ़ॉरवर्ड किए गए संदेश जाँचता हूँ। मुझे संदेश, स्क्रीनशॉट, वॉइस नोट, PDF या लिंक भेजें। "
            "मैं बताऊँगा कि हर दावा सत्यापित, गलत, पुराना, आंशिक रूप से सही या अपुष्ट है, सबूत के साथ।\n\n"
            "भाषा चुनने के लिए HINDI, MARATHI या ENGLISH लिखें।"
        ),
        "mr": (
            "नमस्कार! मी फॉरवर्ड केलेले संदेश तपासतो. मला संदेश, स्क्रीनशॉट, व्हॉइस नोट, PDF किंवा लिंक पाठवा. "
            "प्रत्येक दावा खरा, खोटा, कालबाह्य, अंशतः बरोबर की अपुष्ट आहे ते मी पुराव्यासह सांगेन.\n\n"
            "भाषा निवडण्यासाठी HINDI, MARATHI किंवा ENGLISH लिहा."
        ),
    },
    "lang_set": {
        "en": "Okay, I'll reply in English.",
        "hi": "ठीक है, मैं हिंदी में जवाब दूँगा।",
        "mr": "ठीक आहे, मी मराठीत उत्तर देईन.",
    },
}


def t(key: str, lang: str, **fmt) -> str:
    block = STR[key]
    s = block.get(lang) or block["en"]
    return s.format(**fmt) if fmt else s


def label_name(label: str, lang: str) -> str:
    return LABELS[label].get(lang) or LABELS[label]["en"]


def norm_lang(code: str | None) -> str:
    code = (code or "en").lower()[:2]
    return code if code in SUPPORTED else "en"
