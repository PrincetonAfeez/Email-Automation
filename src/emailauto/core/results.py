""" Results for EmailAuto."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SendResultKind = Literal["success", "transient_failure", "permanent_failure"]


@dataclass(frozen=True)
class RenderedEmail:
    to_email: str
    subject: str
    body: str
    body_format: str
    from_email: str
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    result: SendResultKind
    provider: str
    error_code: str = ""
    error_message: str = ""
    response_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, provider: str, **metadata: Any) -> SendResult:
        return cls("success", provider, response_metadata=metadata)

    @classmethod
    def transient_failure(cls, provider: str, code: str, message: str, **metadata: Any) -> SendResult:
        return cls("transient_failure", provider, code, message, metadata)

    @classmethod
    def permanent_failure(cls, provider: str, code: str, message: str, **metadata: Any) -> SendResult:
        return cls("permanent_failure", provider, code, message, metadata)

