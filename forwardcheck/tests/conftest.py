import pytest

from app import store
from app.llm import LLMError
from app.models import Claim, ClaimList, Evidence, Label, Verdict


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    store.reset_for_tests(str(tmp_path / "t.db"))
    yield


class FakeLLM:
    """Deterministic stand-in so pipeline logic can be tested without network or keys."""

    def __init__(self, claims=None, verdict=None, language="en"):
        self.claims = claims if claims is not None else [
            Claim(text="The government gives Rs 5000 to every family.", text_en="The government gives Rs 5000 to every family.",
                  category="government_scheme", check_worthiness=9, search_queries=["govt Rs 5000 every family"])]
        self.verdict = verdict
        self.language = language
        self.calls = {"claims": 0, "verdict": 0}

    def providers(self):
        return ["fake"]

    async def json(self, system, user, model, media=None):
        if model is ClaimList:
            self.calls["claims"] += 1
            return ClaimList(language=self.language, claims=[c.model_copy() for c in self.claims]), "fake"
        if model is Verdict:
            self.calls["verdict"] += 1
            return (self.verdict or Verdict(label=Label.FALSE, what_is_wrong="Amount is wrong.", summary="Not true.",
                                            evidence_ids=["e1"], evidence_stances={"e1": "contradicts"},
                                            confidence="high")), "fake"
        raise AssertionError(model)

    async def text(self, *a, **k):
        raise LLMError("no text provider in tests")


def ev(i="e1", date="2026-03-12", snippet="PIB: No such scheme exists.", name="PIB Fact Check"):
    return Evidence(id=i, source_name=name, domain="pib.gov.in", url="https://pib.gov.in/x", published_at=date,
                    snippet=snippet, kind="web", relevance=0.5)
