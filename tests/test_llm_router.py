import pytest
import asyncio

from app.ai.intent import IntentResult
from app.ai.llm.base import InvalidStructuredOutputError, LLMUnavailableError, ProviderRequestError
from app.ai.llm.router import LLMRouter


class Provider:
    def __init__(self, name, outcomes):
        self.name = name
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_structured(self, *, system, user, schema, timeout_s):
        self.calls += 1
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_router_fails_over_after_provider_error():
    expected = IntentResult(intent="smalltalk", summary="Hello")
    first = Provider("first", [ProviderRequestError("rate limited")])
    second = Provider("second", [expected])
    router = LLMRouter([first, second], cloud_timeout_s=1, local_timeout_s=2)

    result = await router.generate_structured(system="system", user="hello", schema=IntentResult)

    assert result == expected
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_invalid_output_gets_one_repair_attempt():
    expected = IntentResult(intent="smalltalk", summary="Hello")
    provider = Provider("first", [InvalidStructuredOutputError(), expected])
    router = LLMRouter([provider], cloud_timeout_s=1, local_timeout_s=2)

    assert await router.generate_structured(system="system", user="hello", schema=IntentResult) == expected
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_all_provider_failures_raise_typed_error():
    provider = Provider("first", [ProviderRequestError("offline"), ProviderRequestError("offline")])
    router = LLMRouter([provider], cloud_timeout_s=1, local_timeout_s=2)

    with pytest.raises(LLMUnavailableError):
        await router.generate_structured(system="system", user="hello", schema=IntentResult)


@pytest.mark.asyncio
async def test_circuit_breaker_skips_provider_during_cooldown_and_recovers():
    expected = IntentResult(intent="smalltalk", summary="Hello")
    provider = Provider("first", [ProviderRequestError("offline"), expected])
    router = LLMRouter(
        [provider],
        cloud_timeout_s=1,
        local_timeout_s=2,
        breaker_failures=1,
        breaker_cooldown_s=0.02,
    )

    with pytest.raises(LLMUnavailableError):
        await router.generate_structured(system="system", user="hello", schema=IntentResult)
    with pytest.raises(LLMUnavailableError):
        await router.generate_structured(system="system", user="hello", schema=IntentResult)
    assert provider.calls == 1

    await asyncio.sleep(0.03)
    assert await router.generate_structured(system="system", user="hello", schema=IntentResult) == expected
