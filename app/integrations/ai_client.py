from dataclasses import dataclass
from typing import Protocol


class AIClient(Protocol):
    async def extract_meeting_decisions(self, source_text: str) -> list["DecisionDraft"]:
        ...


@dataclass(frozen=True)
class DecisionDraft:
    title: str
    owner_id: str | None
    completion_criteria: str | None
    tdl_title: str
    due_at_hint: str | None


class PlaceholderAIClient:
    """Deterministic fallback used until provider wiring is added."""

    async def extract_meeting_decisions(self, source_text: str) -> list[DecisionDraft]:
        lines = [line.strip("- ").strip() for line in source_text.splitlines() if line.strip()]
        if not lines:
            return []
        first_line = lines[0][:500]
        return [
            DecisionDraft(
                title=first_line,
                owner_id=None,
                completion_criteria=None,
                tdl_title=first_line,
                due_at_hint=None,
            )
        ]
