# PS3: Is This Forward True? Detailed Plan

## 0. Rulebook constraints (from rulebook.pdf and the PPT template; these override the rest of this plan)
- **No pre-built code.** "Use of pre-built or substantially pre-developed projects is prohibited and may lead to disqualification." Do NOT write the project before Oct 15. Allowed prep: accounts and API keys, reading docs, choosing the stack, designing the architecture, writing the test claims, rehearsing. Build starts at the 10:00 AM kickoff. Standard libraries and APIs are fine.
- **Misleading or non-functional demos can disqualify.** No hard-coded answers for demo claims, and do not show a cached result as if it were a live run. Pre-warming the cache is only safe if the results come from the real pipeline, and you should say so if asked.
- **Your PS in Round 2 may not be PS3.** The PS PDF is marked "only applicable for ppt round". At check-in you randomly pick a colour that maps to PS 1, PS 2 or Open Innovation within your domain, revealed at the 9:00 AM inauguration, and it is locked. If you get Open Innovation you may stay on it or switch to a predefined PS, and you must decide before kickoff. So prepare for the whole domain, not only PS3.
- **Domain name mismatch:** the rulebook lists domains as AIML, Cyber Security, Fintech, Blockchain, while the PS PDF calls PS3's domain GenAI. Check what Unstop's domain field says and use that exact label on slide 1.
- **PPT rules:** max **7 slides including the title slide**, use the official template without changing its content pointers, bullets/diagrams not paragraphs, a flow diagram is recommended, **save as PDF only**. Delete the Rules slide. The template has 6 content slides, so you have 1 spare slide.
- **Schedule:** build only from 10:00 AM (Oct 15) to the final git push at 9:45 AM (Oct 16); stop development at 10:00 AM. Git pushes are scheduled at 1:00 PM, 5:00 PM, 8:00 PM, 12:00 AM, 6:30 AM and 9:45 AM. Judging is 10:15 AM-12:00 PM, Top 10 announced 12:30 PM, final 1:30-3:00 PM (7 min + 3 min Q&A, hard buzzer at 7, no extra time past 8). The prototype must be shown. **Formal attire on final day.**
- **Network/security rules:** use trusted tools only, no unauthorized downloads, no prohibited LAN. College Wi-Fi may block ngrok/Twilio webhooks, so have a mobile hotspot ready and tell organizers if something is blocked. Install your dependencies and tools the day before.
- **Eligibility:** undergraduates only, bring student ID, each person in one team only, team of 3 is final before the event.
- **Plagiarism:** using open-source libraries and public APIs is normal, but do not copy someone else's project or code and present it as yours.

## 1. Product in one line
A WhatsApp bot. Users forward a message, screenshot, voice note, PDF or URL. The bot extracts the checkable claims, verifies each against reliable sources, and replies per claim with a verdict, the evidence, and a plain-language explanation in the user's language.

Verdicts (fixed set): **Verified | False | Outdated | Partly supported | Cannot be confirmed**

## 2. Requirements checklist (from the PS)
- [ ] Input: WhatsApp message text
- [ ] Input: screenshot
- [ ] Input: voice note
- [ ] Input: PDF (including long ones)
- [ ] Input: URL
- [ ] Verification against reliable sources (not model memory)
- [ ] Supporting evidence shown for every verdict
- [ ] Simple-language explanation
- [ ] All five verdict states, incl. "cannot be confirmed" when evidence is absent
- [ ] Non-English users supported (input and output)
- [ ] States what exactly is wrong and why (claim-level, not bare true/false)

## 3. Architecture

```
WhatsApp user
   |  (Twilio WhatsApp webhook)
   v
FastAPI backend
   1. Ingest router  -> type detect (text / image / audio / pdf / url)
        text   : as-is
        image  : vision-LLM OCR (fallback Tesseract)
        audio  : speech-to-text (Hindi/Marathi/English) + language detect
        pdf    : PyMuPDF text -> chunk -> claim-dense chunk selection
        url    : trafilatura article extract (+ publish date)
   2. Normalize       -> clean text + detected language + source metadata
   3. Claim extractor -> LLM returns JSON list of atomic, checkable claims
                         (drops opinions/greetings), each with category + date sensitivity
   4. Cache lookup    -> embedding similarity on previously checked claims
   5. Retriever       -> per claim: Google Fact Check API + allowlisted-domain web search
                         -> fetch pages -> pull snippets with publish dates
   6. Judge           -> LLM sees ONLY claim + retrieved evidence; outputs verdict,
                         what's wrong, cited evidence IDs, confidence
   7. Guardrails      -> every verdict must cite >=1 evidence snippet, else forced to
                         "Cannot be confirmed"
   8. Explainer       -> plain-language summary in user's language (+ TTS audio)
   9. Reply builder   -> WhatsApp message(s) per claim (+ optional voice note)
   |
Datastore: SQLite/Postgres (claims, evidence, verdicts, cache) + web dashboard
```

## 4. Tech stack

| Layer | Choice | Why / fallback |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Fast to write, async, good AI libs |
| WhatsApp | Twilio WhatsApp Sandbox | Live in minutes. Fallback: web app with same API |
| LLM (extract/judge/explain) | **OpenRouter free models (`:free` suffix)** via the OpenAI-compatible API, JSON output + schema validation + retry | No paid key needed. Model list changes often, so pick from openrouter.ai/models (filter: free) and keep model names in config |
| LLM fallback chain | Google Gemini free tier (AI Studio key) and/or Groq free tier | Free OpenRouter models have tight daily/per-minute limits, so a second provider keeps the demo alive |
| Screenshot OCR | Tesseract/EasyOCR (Hindi + Marathi + English packs) first; free vision model (OpenRouter or Gemini) as a second pass | OCR is local and unlimited; vision LLM handles messy layouts |
| Speech-to-text | Groq free Whisper large-v3 API, or local faster-whisper | Hindi/Marathi support; local = no limits but needs CPU/GPU. Optional: Sarvam AI free credits |
| Text-to-speech | gTTS (free) / Sarvam Bulbul free credits | Voice reply for low-literacy users (stretch) |
| PDF | PyMuPDF (fitz) | Fast text extraction |
| URL | trafilatura (+ requests) | Clean article text + date |
| Fact-check source | Google Fact Check Tools API | Free; returns existing ClaimReview from fact-checkers |
| Web search | Tavily or Brave Search API, restricted to allowlisted domains | Retrieval of fresh evidence |
| Embeddings / cache | sentence-transformers (multilingual MiniLM) + SQLite, or pgvector | Dedup repeated forwards |
| DB | SQLite for hackathon (Supabase/Postgres if needed) | Zero setup |
| Dashboard (backup demo + stats) | React/Next.js or plain HTML + Tailwind | Fallback if WhatsApp fails |
| Hosting | Render/Railway, or local + ngrok for the demo | Twilio needs a public webhook URL |

### Reliable-source allowlist (starting point)
- Government: pib.gov.in (PIB Fact Check), india.gov.in, mohfw.gov.in, ministry sites, RBI, SEBI, ECI
- Health: who.int, icmr.gov.in, nhp.gov.in
- Fact-checkers (IFCN signatories): Alt News, BOOM, Factly, Vishvas News, Newschecker, Reuters Fact Check, AFP Fact Check, Snopes
- News: The Hindu, Indian Express, PTI, Reuters, BBC
Keep it as a config file so it's easy to extend and easy to defend in Q&A.

### Working with free LLMs: required adjustments
- **Provider abstraction:** one `llm.call(task, prompt)` function; the model/provider per task and the fallback order live in config. Switching models costs nothing.
- **Rate limits:** OpenRouter free models are limited per minute and per day (the limit rises if you add a small credit balance; check current numbers on their site). Plan for it:
  cache aggressively, cap claims per submission at 3-5, run retrieval in parallel but LLM calls sparingly, add retry with backoff, and fall back to the next provider on 429/errors.
- **Weaker JSON discipline:** validate every output with Pydantic, retry once with the error message, and keep prompts short with one worked example.
- **Fewer LLM calls per claim:** merge extract + normalize into one call, and judge + explain into one call where possible.
- **Quality for Indic languages varies by model:** test 2-3 free models on your own Hindi/Marathi samples in the first hours and pick per task. Use English for retrieval and judging, and translate only the final explanation.
- **Demo safety:** do not hard-code demo answers (see section 0); keep a second API key/provider ready, and keep the recorded backup video.
- **Do not let the LLM be the source of truth.** With weaker models, the retrieval-grounded rule (cite evidence or return "Cannot be confirmed") matters even more.

## 5. Verdict rubric (put this in the judge prompt and the PPT)
- **Verified**: current, reliable sources directly support the claim in full.
- **False**: reliable sources directly contradict the claim.
- **Outdated**: was true at some point, but newer reliable sources show it has changed or expired (check dates).
- **Partly supported**: some parts of the claim hold and others do not, or the claim is exaggerated or lacks context. Always state which part is which.
- **Cannot be confirmed**: no reliable source supports or contradicts it. Never guess.

## 6. Per-claim reply format (WhatsApp)
```
Claim: "<short restatement>"
Verdict: PARTLY SUPPORTED
What's wrong: The scheme exists, but the Rs 5,000 amount is wrong. Official amount is Rs 2,000.
Evidence:
 1. PIB Fact Check (12 Mar 2026): <one-line quote> <link>
 2. <source> (<date>): <quote> <link>
Simple summary: <2 short sentences in user's language>
```

## 7. Data model (minimal)
- `submissions(id, user, input_type, raw_ref, language, created_at)`
- `claims(id, submission_id, text, category, embedding)`
- `evidence(id, claim_id, source_domain, url, snippet, published_at, retrieved_at)`
- `verdicts(id, claim_id, label, what_is_wrong, explanation, confidence, evidence_ids, language)`

## 8. Key design decisions (judges will ask)
1. **Why won't it hallucinate verdicts?** Judge sees only retrieved evidence, must cite evidence IDs, and falls back to "Cannot be confirmed" with no citation.
2. **How does it find the claim in a long PDF or voice note?** Chunk the text, score chunks for claim density, extract atomic claims, then rank by check-worthiness. Cap at about 3-5 claims per submission and say so.
3. **How does it detect "outdated"?** Every evidence snippet carries a publish date, and the claim carries a time-sensitivity flag. The judge compares them.
4. **Language?** Detect language, translate the claim to English for retrieval (most sources are English), and write the explanation back in the user's language.
5. **Bias in sources?** The allowlist is transparent and configurable, and evidence always shows the source.
6. **Privacy?** Don't store raw media beyond processing. Store only extracted claims. Mention this in the PPT.

## 9. 24-hour build timeline (Round 2, Oct 15-16), aligned with the official git pushes
Build window: 10:00 AM Oct 15 to 9:45 AM Oct 16. Start from an empty repo at kickoff. Push at every scheduled slot, and commit often in between.

| Time | Goal | Git push |
|---|---|---|
| 10:00-11:00 | Repo, env, keys loaded, Twilio sandbox echo bot, `llm.call()` wrapper with provider fallback | |
| 11:00-1:00 PM | Ingestion v1: text + URL + PDF -> clean text; claim extractor (JSON, validated) | **1:00 PM:** skeleton + ingestion + echo bot |
| 1:00-5:00 PM | Retriever (Fact Check API + allowlisted search) + judge + guardrail; end-to-end on text claims; image OCR; STT | **5:00 PM:** text claims verified end to end |
| 5:00-8:00 PM | All 5 input types working; WhatsApp reply format; language detect + translation | **8:00 PM:** all inputs in one pipeline |
| 8:00 PM-12:00 AM | Multilingual explanation (Hindi/Marathi), five-verdict tuning on test set, web UI fallback | **12:00 AM:** multilingual + web UI |
| 12:00 AM-6:30 AM | Sleep in shifts (one person always awake). Fix failures from the test set, caching, error handling, rate-limit handling | **6:30 AM:** stable build |
| 6:30-9:45 AM | Freeze features, README, record backup demo video, rehearse pitch | **9:45 AM:** final push |
| 10:00 AM | Stop development. | |
| 10:15-12:00 | Round 2 judging: live demo to judges | |
| 1:30-3:00 PM | If Top 10: 7 min + 3 min Q&A, formal attire | |

Rule of thumb: by the 5:00 PM push, a text claim should go all the way to a cited verdict. If it doesn't, cut scope (for example voice-note TTS) rather than add features.

## 10. Team split (3 people)
- **A: Ingestion + multilingual** (OCR, STT, PDF, URL, language detect, translation, Hindi/Marathi quality)
- **B: Verification core** (claim extraction, retrieval, judge, guardrails, test set and evaluation)
- **C: WhatsApp/backend glue + demo** (Twilio, FastAPI, reply formatting, hosting/hotspot, web UI fallback, README, pitch)
Everyone writes demo claims and tests. Agree interfaces on day 1 (function signatures and the JSON schema for claims/evidence/verdicts) so the three parts plug together. If you get a different PS in your domain, the same split still applies.

## 11. Demo script (7 minutes)
1. 30s: the problem (one real forward that went viral).
2. 4 min live demo on WhatsApp, 5 prepared forwards:
   - Hindi/Marathi voice note -> **False**, with the reason
   - Screenshot of a "new scheme" -> **Partly supported** or **Outdated**
   - Long PDF -> per-claim breakdown
   - URL of a news article -> **Verified**
   - Obscure unverifiable claim -> **Cannot be confirmed**
3. 1 min: architecture + guardrail (why it won't make things up).
4. 1.5 min: impact, SDG mapping, roadmap.
Have a recorded backup video and the web UI ready in case WhatsApp or the network fails.

## 12. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Twilio sandbox or network fails at demo | Web UI fallback + recorded video |
| LLM latency makes the demo feel slow | Cache, parallel retrieval, "checking..." status message |
| Search returns irrelevant or no evidence | Allowlist + Fact Check API first; default to "Cannot be confirmed" |
| Poor Indic OCR or STT | Test early on real samples, pick the best engine, keep a fallback |
| Free-tier rate limits / model removal | Provider fallback chain, cache, claim cap, model names in config |
| Weaker free-model accuracy | Evidence-only judging, schema validation, test-set evaluation to pick the best model per task |
| Judges test with their own forward | Generalize the pipeline; avoid hard-coding demo answers |

## 13. Evaluation (to show feasibility)
Build a small labeled test set (about 30-40 claims across all five verdicts and all input types, in at least 2 languages). Report verdict accuracy and evidence-citation rate on it. One slide of real numbers is far stronger than claims of accuracy.

## 14. Round 1 PPT (due Oct 10, 11:59 PM IST), follows the official template
Max 7 slides including title, PDF only, bullets and diagrams, no paragraphs, delete the Rules slide.

1. **Title slide:** Team name, Domain (use Unstop's exact label), Problem statement title ("Is This Forward True?"), Abstract (3-4 lines), Video/Prototype link (optional, a short mockup video helps)
2. **Problem Statement:** what the problem is, who is affected, pain points, why it needs solving, existing solutions (fact-check sites, tiplines) and their gaps, 2-3 real statistics (verify each before using)
3. **Proposed Solution:** what it is, how it solves the problem, user journey, target users, input -> solution -> output, **flow diagram** (the pipeline from section 3)
4. **Innovation & Key Features** (3-5): all five input types; claim-level verdicts with evidence; five-state verdict incl. "outdated" and "cannot be confirmed"; multilingual (English/Hindi/Marathi) with voice; evidence-only judging so it doesn't hallucinate; USP line
5. **Technology and Implementation:** stack, models, APIs, architecture, data/source list, prototype status, how it will be implemented
6. **Impact and Future Scope:** expected impact, who benefits, KPIs (verdict accuracy on a test set, citation rate, response time), scalability, feasibility, future enhancements, real-world deployment, long-term vision; SDG 4, 9, 16 mapping
7. (spare) **Example result card / screenshots mockup** of a WhatsApp reply, which makes the idea concrete in seconds

Do not claim features or numbers you haven't verified. The jury is evaluating innovation, feasibility and relevance.

## 15. Open items
- Create free accounts/keys now (allowed prep, no project code): OpenRouter, Google AI Studio, Groq, Twilio, Tavily (or the keyless `duckduckgo-search` library as a fallback). Check each free tier's current limits yourself.
- Decide the Domain label for slide 1 (AIML vs GenAI) from Unstop.
- Decide roles A/B/C.
- Collect 30-40 test claims (as text files/screenshots/audio) in English/Hindi/Marathi with known answers. Test data is allowed prep, code is not.
- Check that college Wi-Fi allows webhooks; plan a hotspot.
