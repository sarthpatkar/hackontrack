"""Settings and the reliable-source allowlist."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Tesseract language data (eng + hin + mar) shipped in ./tessdata
os.environ.setdefault("TESSDATA_PREFIX", str(ROOT / "tessdata"))

# domain -> (display name, group). Subdomains match automatically.
ALLOWLIST: dict[str, tuple[str, str]] = {
    # Government of India
    "pib.gov.in": ("PIB", "government"),
    "india.gov.in": ("National Portal of India", "government"),
    "mygov.in": ("MyGov", "government"),
    "rbi.org.in": ("Reserve Bank of India", "government"),
    "sebi.gov.in": ("SEBI", "government"),
    "eci.gov.in": ("Election Commission of India", "government"),
    "mohfw.gov.in": ("Ministry of Health & Family Welfare", "health"),
    "icmr.gov.in": ("ICMR", "health"),
    "nhp.gov.in": ("National Health Portal", "health"),
    "indiabudget.gov.in": ("Union Budget", "government"),
    # Health bodies
    "who.int": ("World Health Organization", "health"),
    "cdc.gov": ("US CDC", "health"),
    "nhs.uk": ("NHS", "health"),
    "nih.gov": ("US National Institutes of Health", "health"),
    "cancer.gov": ("US National Cancer Institute", "health"),
    "cancer.org": ("American Cancer Society", "health"),
    "cancerresearchuk.org": ("Cancer Research UK", "health"),
    "mayoclinic.org": ("Mayo Clinic", "health"),
    "medlineplus.gov": ("MedlinePlus", "health"),
    # Fact-checkers
    "altnews.in": ("Alt News", "fact_check"),
    "boomlive.in": ("BOOM", "fact_check"),
    "factly.in": ("Factly", "fact_check"),
    "newschecker.in": ("Newschecker", "fact_check"),
    "vishvasnews.com": ("Vishvas News", "fact_check"),
    "factcheck.afp.com": ("AFP Fact Check", "fact_check"),
    "reuters.com": ("Reuters", "news"),
    "apnews.com": ("Associated Press", "news"),
    "snopes.com": ("Snopes", "fact_check"),
    "factcheck.org": ("FactCheck.org", "fact_check"),
    "thequint.com": ("The Quint", "news"),
    # News
    "thehindu.com": ("The Hindu", "news"),
    "indianexpress.com": ("The Indian Express", "news"),
    "ptinews.com": ("PTI", "news"),
    "bbc.com": ("BBC", "news"),
    "bbc.co.uk": ("BBC", "news"),
}

# Any *.gov.in / *.nic.in host counts as an official government source.
GOV_SUFFIXES = (".gov.in", ".nic.in")

# Where to look first for each claim category (site: searches).
CATEGORY_DOMAINS: dict[str, list[str]] = {
    "health": ["who.int", "nih.gov", "cancer.gov", "mohfw.gov.in", "icmr.gov.in"],
    "government_scheme": ["pib.gov.in", "india.gov.in", "mygov.in"],
    "finance": ["rbi.org.in", "sebi.gov.in", "pib.gov.in"],
    "news": ["reuters.com", "thehindu.com", "pib.gov.in"],
    "science": ["who.int", "reuters.com"],
    "other": ["pib.gov.in", "reuters.com"],
}
FACT_CHECK_DOMAINS = ["altnews.in", "boomlive.in", "factly.in", "newschecker.in", "vishvasnews.com"]


def source_info(url: str) -> tuple[str, str] | None:
    """Return (display name, domain) if the URL is on the allowlist, else None."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    best = None
    for domain, (name, _group) in ALLOWLIST.items():  # longest matching domain wins
        if (host == domain or host.endswith("." + domain)) and (best is None or len(domain) > len(best[1])):
            best = (name, domain)
    if best:
        return best
    if host.endswith(GOV_SUFFIXES):
        return host, host
    return None


@dataclass
class Settings:
    gemini_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    groq_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openrouter_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    groq_models: list[str] = field(
        default_factory=lambda: [m.strip() for m in os.getenv("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]
    )
    openrouter_models: list[str] = field(
        default_factory=lambda: [m.strip() for m in os.getenv("OPENROUTER_MODELS", "").split(",") if m.strip()]
    )
    gemini_base: str = field(default_factory=lambda: os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"))
    groq_base: str = field(default_factory=lambda: os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    openrouter_base: str = field(default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    factcheck_key: str = field(default_factory=lambda: os.getenv("GOOGLE_FACTCHECK_API_KEY", ""))
    tavily_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    twilio_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_from: str = field(default_factory=lambda: os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"))
    public_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "").rstrip("/"))
    validate_twilio: bool = field(default_factory=lambda: os.getenv("VALIDATE_TWILIO", "1") != "0")

    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    )

    # limits
    max_claims: int = 5
    max_upload_bytes: int = 16 * 1024 * 1024
    max_pdf_pages: int = 60
    max_text_chars: int = 60_000
    max_parallel_claims: int = 2
    max_evidence: int = 6
    cache_ttl_seconds: int = 24 * 3600
    cache_ttl_time_sensitive_seconds: int = 3 * 3600
    rate_limit_per_minute: int = 20
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", str(ROOT / "data" / "forwardcheck.db")))


settings = Settings()
