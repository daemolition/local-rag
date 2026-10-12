# Local Document RAG - A privacy-focused, local RAG system
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

"""Aufbau des Chat-LLMs (OpenAI-kompatibel) aus Endpunkt und Parametern."""

import os

from langchain_openai import ChatOpenAI

_FALLBACK = {
    "temperature": "0.1",
    "top_p": "0.2",
    "top_k": "40",
    "max_tokens": "",
    "num_ctx": "4096",
    "thinking": "none",
}
_SETTING_KEYS = {
    "temperature": "CHAT_TEMPERATURE",
    "top_p": "CHAT_TOP_P",
    "top_k": "CHAT_TOP_K",
    "max_tokens": "CHAT_MAX_TOKENS",
    "num_ctx": "CHAT_NUM_CTX",
    "thinking": "CHAT_THINKING",
}


def global_chat_defaults() -> dict:
    """Globale Sampling-Einstellungen (Settings-DB, sonst env, sonst Default).

    Sie gelten fuer jedes Modell, das einen Parameter nicht selbst setzt.
    """
    raw = dict(_FALLBACK)
    try:
        from app.database_service import get_db_service
        from app.settings_service import SettingsService

        session = get_db_service().get_session()
        try:
            settings = SettingsService(session)
            for name, key in _SETTING_KEYS.items():
                raw[name] = settings.get(key, raw[name]) or raw[name]
            # leerer Wert ist bei max_tokens gueltig (= unbegrenzt)
            raw["max_tokens"] = settings.get("CHAT_MAX_TOKENS", "") or ""
        finally:
            session.close()
    except Exception:
        for name, key in _SETTING_KEYS.items():
            raw[name] = os.getenv(key, raw[name])

    return {
        "temperature": float(raw["temperature"] or 0.1),
        "top_p": float(raw["top_p"] or 0.2),
        "top_k": int(raw["top_k"] or 40),
        "max_tokens": int(raw["max_tokens"]) if str(raw["max_tokens"]).strip() else None,
        "num_ctx": int(raw["num_ctx"] or 4096),
        "thinking": raw["thinking"] or "none",
    }


def build_chat_llm(
    base_url: str,
    api_key: str,
    model: str,
    params: dict | None = None,
    streaming: bool = True,
    timeout: float | None = None,
) -> ChatOpenAI:
    """Baut das Chat-LLM. ``params`` ueberschreibt die globalen Defaults."""
    p = {**global_chat_defaults(), **(params or {})}

    # extra_body wird vom OpenAI-SDK ungeprueft im Request mitgeschickt - ideal
    # fuer provider-spezifische Parameter wie top_k und num_ctx. (model_kwargs
    # wuerden als top-level kwargs validiert und vom SDK abgelehnt.)
    extra_body = {}
    if p.get("top_k"):
        extra_body["top_k"] = p["top_k"]
    if p.get("num_ctx"):
        extra_body["num_ctx"] = p["num_ctx"]

    kwargs = {
        "model": model,
        "base_url": base_url,
        "api_key": api_key or "none",
        "streaming": streaming,
        "temperature": p["temperature"],
        "top_p": p["top_p"],
    }
    if p.get("max_tokens") is not None:
        kwargs["max_tokens"] = p["max_tokens"]
    if timeout is not None:
        kwargs["timeout"] = timeout

    # Thinking/Reasoning:
    # - Ollama nutzt reasoning_effort (none/low/medium/high/max).
    # - llama.cpp parst Think-Tags standardmaessig und liefert Thinking als
    #   reasoning_content, das langchain-openai (v1.x) nicht in additional_kwargs
    #   durchreicht. Daher reasoning_format=none: die Tags bleiben inline im
    #   content und das Frontend zeigt sie als ausklappbaren Block.
    #   reasoning_effort=none deaktiviert Thinking explizit.
    thinking = p.get("thinking") or "none"
    if thinking != "none":
        kwargs["reasoning_effort"] = thinking
        extra_body["reasoning_format"] = "none"
    else:
        kwargs["reasoning_effort"] = "none"

    if extra_body:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)
