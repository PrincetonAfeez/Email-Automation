from __future__ import annotations


class EmailAutomationError(Exception):
    """Base application exception."""


class InvalidStateTransition(EmailAutomationError):
    """Raised when a model lifecycle transition is not allowed."""


class StaleClaimToken(EmailAutomationError):
    """Raised when a worker without the current claim tries to mutate a row."""


class TemplateRenderError(EmailAutomationError):
    """Raised when a template cannot be safely rendered."""


class MissingTemplateVariable(TemplateRenderError):
    def __init__(self, variable: str) -> None:
        super().__init__(f"Missing required template variable: {variable}")
        self.variable = variable


class PermanentSendError(EmailAutomationError):
    """A failure that should not be retried."""


class TransientSendError(EmailAutomationError):
    """A failure that may be retried."""

