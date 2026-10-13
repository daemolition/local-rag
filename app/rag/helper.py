# Open Knowledge UI - A privacy-focused, self-hosted RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Helfer-LLM fuer das Query-Enhancement."""

from collections.abc import Callable

from app.access import can_use_model
from app.llm import registry
from app.llm.factory import build_chat_llm


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # Inhaltsbloecke
        return "".join(
            b if isinstance(b, str) else b.get("text", "") for b in content if b
        )
    return str(content)


def make_helper(
    chat_model: "registry.ResolvedModel | None", user: dict
) -> Callable[[str, dict], str] | None:
    """Liefert ``helper(prompt, qe_config) -> Text``.

    Nutzt das gerade chattende Modell, es sei denn das Profil nennt ein eigenes
    (``model_ref``; dann muss der Nutzer es verwenden duerfen). Immer ohne
    Thinking und ohne Begrenzung der Ausgabelaenge. ``None``, wenn es kein Modell gibt.
    """
    if chat_model is None:
        return None

    def helper(prompt: str, qe: dict) -> str:
        target = chat_model
        if qe.get("model_ref"):
            target = registry.resolve_model(qe["model_ref"])
            if not can_use_model(user, target.ref):
                raise PermissionError("Kein Zugriff auf das Helfer-Modell des Profils")
        llm = build_chat_llm(
            target.base_url,
            target.api_key,
            target.model_id,
            {"temperature": qe["temperature"], "thinking": "none", "max_tokens": None},
            streaming=False,
            timeout=qe["timeout_s"],
        )
        return _text(llm.invoke(prompt).content)

    return helper
