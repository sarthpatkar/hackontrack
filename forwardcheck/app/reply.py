"""Format results as WhatsApp text (<= 1600 chars per message, one card per claim)."""
from __future__ import annotations

from .i18n import EMOJI, label_name, t
from .models import CheckResult, ClaimResult

LIMIT = 1500


def _trim(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def format_card(r: ClaimResult, lang: str, snippet_len: int = 140) -> str:
    v = r.verdict
    lines = [f"*{t('claim', lang)}:* {_trim(r.claim.text, 200)}",
             f"*{t('verdict', lang)}:* {EMOJI[v.label.value]} {label_name(v.label.value, lang)}"]
    if v.what_is_wrong:
        lines.append(f"*{t('wrong', lang)}:* {_trim(v.what_is_wrong, 380)}")
    cited = [e for e in r.evidence if e.id in v.evidence_ids][:3]
    if cited:
        lines.append(f"*{t('evidence', lang)}:*")
        for n, e in enumerate(cited, 1):
            when = f" ({e.published_at})" if e.published_at else ""
            lines.append(f"{n}. {e.source_name}{when}: “{_trim(e.snippet, snippet_len)}”\n{e.url}")
    if v.summary and v.summary != v.what_is_wrong:
        lines.append(f"*{t('summary', lang)}:* {_trim(v.summary, 260)}")
    return "\n".join(lines)


def format_messages(res: CheckResult) -> list[str]:
    lang = res.language
    if not res.results:
        return [t("no_claims", lang)]
    msgs = []
    for r in res.results:
        card = format_card(r, lang)
        if len(card) > LIMIT:
            card = format_card(r, lang, snippet_len=70)
        msgs.append(card[:LIMIT])
    if res.note and "Found" in res.note:
        msgs.insert(0, t("more_claims", lang, n=len(res.results)))
    msgs[-1] = (msgs[-1] + "\n\n" + t("footer", lang))[:1600]
    return msgs
