"""Tests for model clients and tier resolution."""

import pytest
from workshop_agent import resolve_model_spec, resolve_client, ModelSpec, Provider
from workshop_agent.model import MockClient


def test_resolve_model_spec_tier_medium():
    spec = resolve_model_spec("medium")
    assert spec.provider == Provider.ANTHROPIC
    assert "sonnet" in spec.model


def test_resolve_model_spec_tier_small():
    spec = resolve_model_spec("small")
    assert spec.provider == Provider.ANTHROPIC
    assert "haiku" in spec.model


def test_resolve_model_spec_raw_openai():
    spec = resolve_model_spec("gpt-4o")
    assert spec.provider == Provider.OPENAI
    assert spec.model == "gpt-4o"


def test_resolve_model_spec_raw_anthropic():
    spec = resolve_model_spec("claude-sonnet-4-6")
    assert spec.provider == Provider.ANTHROPIC
    assert spec.model == "claude-sonnet-4-6"


def test_resolve_model_spec_default():
    spec = resolve_model_spec()
    assert spec.provider == Provider.ANTHROPIC


@pytest.mark.asyncio
async def test_mock_client_reviewer():
    client = MockClient()
    from workshop_agent.types import CompleteArgs, Message, MessageRole, TextBlock
    args = CompleteArgs(
        model=ModelSpec(provider=Provider.MOCK, model="mock"),
        system="# Security reviewer",
        tools=[],
        messages=[Message(role=MessageRole.USER, content=[TextBlock(text="review this")])],
    )
    result = await client.complete(args)
    assert len(result.content) == 1
    text = result.content[0].text  # type: ignore
    assert "severity" in text
    assert result.usage.input_tokens == 0


@pytest.mark.asyncio
async def test_mock_client_judge():
    client = MockClient()
    from workshop_agent.types import CompleteArgs, Message, MessageRole, TextBlock
    args = CompleteArgs(
        model=ModelSpec(provider=Provider.MOCK, model="mock"),
        system="# Judge",
        tools=[],
        messages=[Message(role=MessageRole.USER, content=[TextBlock(text="judge this")])],
    )
    result = await client.complete(args)
    text = result.content[0].text  # type: ignore
    assert "approve" in text
    assert "verdict" in text


def test_resolve_client_returns_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "mock")
    client = resolve_client(ModelSpec(provider=Provider.ANTHROPIC, model="claude-sonnet-4-6"))
    assert isinstance(client, MockClient)
