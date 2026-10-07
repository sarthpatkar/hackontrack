# PPT Content: "Is This Forward True?" (final version)

**Rule used for every line:** it is either (A) a verified fact with a source, (B) a feature the team commits to building in the 24-hour MVP, or (C) clearly labelled "Future scope". Nothing else goes on a slide. This keeps the PPT and the product from differing, which matters because the jury will compare them in Round 2 and Round 3.

Template: official Hack On Track template. Max 7 slides including title. Export as PDF. Delete the Rules slide. Keep the template's headings.

---

## SLIDE 1: Title

- **Team Name:** [your team name]
- **Domain:** [exact label from Unstop]
- **Problem Statement Title:** Is This Forward True?
- **Abstract:**
  - A WhatsApp bot that verifies forwarded claims from text, screenshots, voice notes, PDFs and links
  - Pulls out each claim, checks it against reliable sources, and shows the evidence
  - Gives one verdict per claim: Verified, False, Outdated, Partly supported, or Cannot be confirmed
  - Explains what exactly is wrong, in simple English, Hindi or Marathi
- **Video / Prototype / Deployment link:** leave blank (the prototype is built during the hackathon)

---

## SLIDE 2: Problem Statement

**What is the problem?**
- Forwarded messages (health tips, "new government schemes", breaking news) spread faster than anyone can check them
- The claim is often buried in a screenshot, a voice note or a long PDF
- A bare "true" or "false" doesn't tell people what is wrong, or why

**Who is affected?**
- WhatsApp users in India, especially people not comfortable in English and first-time internet users
- Families and community groups that forward without checking

**Current challenges / pain points**
- Checking by hand means searching, comparing sources and judging dates
- Claims inside images, audio and PDFs can't be searched like text
- Old news gets recycled as new
- Most checks give a label without showing evidence

**Why does it need to be solved?**
- False forwards can cause real harm (health decisions, fraud, panic, violence)
- Verification should be available in the app where the message arrives, and in the user's language

**Existing solutions**
- Fact-check organisations (e.g. PIB Fact Check, Alt News, BOOM) publish checks on their sites and channels
- Gap: they review claims manually, so a user's own forward often has no ready answer; and the user has to go find the check

**Statistics (only verified ones)**
- India is WhatsApp's largest market, with over 500 million users (Statista)
- In 2018, 20+ people were killed by mobs over viral WhatsApp messages in India, and WhatsApp responded by capping forwards to 5 chats in India (Reuters/AFP coverage)
- [Add one more verified statistic with its source if you find one, e.g. a recent Indian misinformation survey. Delete this line if you don't.]

---

## SLIDE 3: Proposed Solution

**What is your solution?**
A WhatsApp bot. The user forwards anything, and gets back a claim-by-claim result with verdict, evidence and a plain-language explanation.

**How does it solve the problem?**
- Accepts text, screenshots, voice notes, PDFs and URLs in one chat
- Extracts the checkable claims (up to 5 per message) and ignores opinions
- Searches reliable sources and fact-checks, then judges each claim using only that evidence
- Replies with what is right, what is wrong, and why

**Key workflow / user journey**
1. User forwards a message to the bot
2. Bot replies "Checking..."
3. Bot sends one result card per claim
4. User can forward the result back to the group

**Target users**
- Everyday WhatsApp users, including Hindi and Marathi speakers

**Input -> solution -> output**
- Input: text / image / audio / PDF / URL
- Solution: extract text -> find claims -> retrieve evidence -> judge -> explain
- Output: verdict + evidence with dates and links + explanation in the user's language

**Flow diagram (draw this large)**
```
Forward --> WhatsApp bot
   --> Input handler: text | image OCR | voice-to-text | PDF text | URL text
   --> Language detection
   --> Claim extraction
   --> Evidence retrieval (fact-check database + trusted-source search)
   --> Evidence-only judging (must cite sources)
   --> Verdict + "what's wrong" + explanation (English / Hindi / Marathi)
   --> WhatsApp reply
```

**The five verdicts (small legend)**
- Verified: reliable sources support it
- False: reliable sources contradict it
- Outdated: it was true, but newer sources show it has changed
- Partly supported: some parts hold, some don't
- Cannot be confirmed: no reliable source either way

**Example result card** (label "illustrative")
Claim / Verdict / What's wrong / Evidence (source + date) / Simple summary

---

## SLIDE 4: Innovation & Key Features

**Key features (all committed for the MVP)**
1. All five input types in one bot: text, screenshot, voice note, PDF, URL
2. Claim-level checking: each claim in a forward gets its own verdict
3. Five-state verdict, including "Outdated" and "Cannot be confirmed"
4. Evidence for every verdict, with source and date, plus what exactly is wrong
5. English, Hindi and Marathi explanations

**What makes it different / USP**
- Evidence-grounded by design: the AI may only use retrieved sources. If it finds none, the answer is "Cannot be confirmed", not a guess
- Date-aware: compares the claim's time frame with source dates to flag "Outdated"
- Works inside WhatsApp, with no new app

**Innovative aspect**
- Finds the claim first, then checks it, so it can handle claims hidden in screenshots, voice notes and long PDFs

**How it improves on existing approaches**
- Handles the user's own forward instead of waiting for a published check
- Shows evidence and reasoning, not only a label

**Use of AI/ML**
- LLM for claim extraction, evidence judging and explanation
- OCR for screenshots, speech-to-text for voice notes

---

## SLIDE 5: Technology and Implementation

**Technology stack (free / open source)**
- Python, FastAPI
- Twilio WhatsApp sandbox
- SQLite

**AI/ML models**
- LLMs through OpenRouter free models, with Gemini and Groq free tiers as fallback
- Whisper for speech-to-text; Tesseract/EasyOCR for OCR, with a vision model as a second pass

**APIs / tools**
- Google Fact Check Tools API, search limited to trusted domains, PyMuPDF (PDF), trafilatura (web pages)

**System architecture**
- The same pipeline as the slide 3 diagram, in four layers: Input -> Processing -> Verification -> Response

**Data / source of truth**
- No model training. Verdicts rely on live, reliable sources: government and health bodies (e.g. PIB, WHO, ICMR), fact-checking organisations, and major news agencies
- The source list is a configurable allowlist

**Current implementation / prototype status**
- Design and tech stack finalised; test claims in English, Hindi and Marathi are being prepared
- The working prototype will be built during the 24-hour hackathon

**How it can be implemented**
- One module per stage, with a common function for calling any LLM provider and automatic fallback
- Every verdict must cite retrieved evidence, or it is forced to "Cannot be confirmed"
- Limits we design for: free-tier rate limits (handled with caching and retries) and a cap of 5 claims per message

---

## SLIDE 6: Impact and Future Scope

**Expected impact**
- Anyone can check a forward in seconds to a minute, in their own language, before sharing it

**Who benefits**
- WhatsApp users, especially regional-language speakers; families and community groups

**Measurable outcomes / KPIs** (we will measure these on our own test set during the hackathon)
- Verdict accuracy on a labelled set of claims
- Share of verdicts that include at least one source (enforced by design)
- Response time per forward
- Coverage: 5 input types, 3 languages

**Scalability**
- Sources and languages are added through configuration
- Moves from the Twilio sandbox to the official WhatsApp Business API for production

**Feasibility**
- Built entirely on free tools and public sources; each stage is a separate module

**Future enhancements (not in the MVP)**
- Voice replies, more Indian languages, image and video manipulation checks, a trending-claims dashboard, community tipline

**Potential real-world deployment**
- A public tipline run with fact-checkers, health departments, NGOs or schools

**Limitations we state openly**
- It verifies only claims that public, reliable sources can confirm or refute; otherwise it says "Cannot be confirmed"
- Accuracy depends on the sources and models, so the user always sees the evidence

**SDG mapping**
- SDG 4: information literacy; SDG 9: AI-based information infrastructure; SDG 16: trustworthy information

---

## SLIDE 7 (optional): Example conversation
- Mock WhatsApp chat: forwarded screenshot -> bot result cards. Label "illustrative mockup"

---

## Consistency checklist (the PPT must match the product)
| PPT says | Product must do by Oct 16 |
|---|---|
| 5 input types | text, image, voice, PDF, URL all work |
| 5 verdicts | all five can be produced; include a demo example of each |
| Evidence for every verdict | evidence source + date + link shown in every reply |
| English, Hindi, Marathi | at least the explanation in all 3; test voice notes in Hindi and Marathi |
| WhatsApp bot | works through the Twilio sandbox on a real phone |
| Cannot be confirmed instead of guessing | guardrail in code, tested with an unverifiable claim |
| Up to 5 claims per message | cap implemented |

If a feature isn't working by the 5 PM push, drop it from the pitch rather than claim it. Voice replies, trending dashboard and extra languages are already listed as future scope, so nothing in the pitch depends on them.

Sources used for slide 2 (check them yourself before citing):
- Statista: WhatsApp users in India, https://www.statista.com/statistics/1146773/whatsapp-users-in-india/
- 2018 lynchings and forward limit: https://fortune.com/2018/07/20/whatsapp-forwarding-india-lynchings and https://www.euronews.com/2018/07/20/whatsapp-to-limit-message-forwarding
