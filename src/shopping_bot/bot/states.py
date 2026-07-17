from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddFlow(StatesGroup):
    """User tapped ➕ Додати and we're waiting for the search query."""

    waiting_for_query = State()
