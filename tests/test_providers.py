from types import SimpleNamespace

import pytest

from aml_poc.models import Assessment
from aml_poc.providers import ConnectionCheck, OpenAIModel


def test_assessment_allows_omitted_verdict_fields():
    result = Assessment(
        summary="The case file is ready for review.",
        summary_evidence_ids=["E1"],
        findings=[{"text": "The alert thresholds were met.", "evidence_ids": ["E1"]}],
        recommendation="escalate",
    )
    assert result.observed == ""
    assert result.next_step == ""
    assert result.innocent_explanation == ""



def test_openai_responses_preserves_roles_schema_and_no_storage():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=ConnectionCheck(status="ok"))

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    model = OpenAIModel("test-model", client)
    result = model.with_structured_output(ConnectionCheck).invoke(
        [("system", "Use cited evidence only"), ("human", "Test")]
    )
    assert result.status == "ok"
    assert captured["input"][1]["role"] == "user"
    assert captured["store"] is False
    assert captured["text_format"] is ConnectionCheck


def test_openai_refusal_cannot_be_used_as_an_assessment():
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(output_parsed=None))
    )
    with pytest.raises(ValueError, match="refused"):
        OpenAIModel("test-model", client).with_structured_output(ConnectionCheck).invoke([("human", "Test")])


def test_openai_image_adapter_retains_media_type():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=ConnectionCheck(status="ok"))

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    OpenAIModel("test-model", client).with_structured_output(ConnectionCheck).invoke(
        [("human", [{"type": "image", "source": {"media_type": "image/png", "data": "sample"}}])]
    )
    assert captured["input"][0]["content"][0]["image_url"] == "data:image/png;base64,sample"


@pytest.mark.parametrize("mode", ["demo", "openai", "claude"])
def test_supported_agent_modes(monkeypatch, mode):
    from aml_poc.config import agent_mode

    monkeypatch.setenv("AML_AGENT_MODE", mode)
    assert agent_mode() == mode


def test_unknown_provider_is_rejected_before_database_access():
    from aml_poc.workflow import Workflow

    with pytest.raises(ValueError, match="demo, claude, or openai"):
        Workflow(None, None, "unused", mode="other")
