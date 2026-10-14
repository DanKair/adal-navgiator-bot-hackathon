from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    name: str

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], timeout_s: float
    ) -> T: ...


class LLMUnavailableError(RuntimeError):
    pass


class InvalidStructuredOutputError(ValueError):
    pass


class ProviderRequestError(RuntimeError):
    def __init__(self, message: str, *, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s
