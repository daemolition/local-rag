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

"""
Externe Vektorspeicher (nur lesen).

Eine externe Quelle erscheint als Knowledge der Art ``external``. Ihre Konfiguration liegt in
``knowledge.source_config``. Nichts wird geraten: URL, Collection, Vektornamen, Feldnamen und
das Embedding-Modell gibt der Anleger an; ``probe_source`` zeigt nur Fakten zum Abgleich.
Es werden ausschliesslich lesende Aufrufe benutzt (query_points, scroll, count, get_collection).
"""

import json
from dataclasses import dataclass, field
from logging import getLogger

from qdrant_client import QdrantClient

logger = getLogger(__name__)

TIMEOUT_S = 20
DEFAULT_FIELDS = {
    "text": "page_content",
    "filename": "filename",
    "title": "title",
    "headers": "headers",
    "page_start": "page_start",
    "page_end": "page_end",
    "chunk_index": "chunk_index",
    "group": "file_group_id",
}
KINDS = ("qdrant",)


class SourceError(Exception):
    """Fachlicher Fehler mit lesbarer Meldung (400/502 in der API)."""


@dataclass(frozen=True)
class SourceConfig:
    kind: str = "qdrant"
    url: str = ""
    api_key: str = field(default="", repr=False)
    collection: str = ""
    dense_vector: str = ""  # leer = unbenannter Vektor
    sparse_vector: str = ""  # leer = keine Stichwortsuche (nur dense)
    fields: dict = field(default_factory=lambda: dict(DEFAULT_FIELDS))

    def to_dict(self, with_key: bool = True) -> dict:
        d = {
            "kind": self.kind,
            "url": self.url,
            "collection": self.collection,
            "dense_vector": self.dense_vector,
            "sparse_vector": self.sparse_vector,
            "fields": dict(self.fields),
        }
        if with_key:
            d["api_key"] = self.api_key
        return d

    def public(self) -> dict:
        """Fuer Antworten an die Oberflaeche: nie der Key."""
        return {**self.to_dict(with_key=False), "has_key": bool(self.api_key)}

    @property
    def uses_default_neighbor_fields(self) -> bool:
        return (
            self.fields.get("chunk_index") == DEFAULT_FIELDS["chunk_index"]
            and self.fields.get("group") == DEFAULT_FIELDS["group"]
        )


def parse_config(raw: dict | str | None) -> SourceConfig:
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    raw = raw or {}
    fields = {**DEFAULT_FIELDS, **{k: (v or DEFAULT_FIELDS[k]) for k, v in (raw.get("fields") or {}).items() if k in DEFAULT_FIELDS}}
    return SourceConfig(
        kind=raw.get("kind") or "qdrant",
        url=(raw.get("url") or "").strip().rstrip("/"),
        api_key=raw.get("api_key") or "",
        collection=(raw.get("collection") or "").strip(),
        dense_vector=(raw.get("dense_vector") or "").strip(),
        sparse_vector=(raw.get("sparse_vector") or "").strip(),
        fields=fields,
    )


def _check_url(url: str) -> None:
    from app.llm.registry import RemoteModelsError, _reject_link_local

    if not url.startswith(("http://", "https://")):
        raise SourceError("Die Adresse muss mit http:// oder https:// beginnen")
    try:
        _reject_link_local(url)
    except RemoteModelsError as e:
        raise SourceError(str(e)) from None


def connect(cfg: SourceConfig) -> QdrantClient:
    """Lese-Client fuer die Quelle (Zeitlimit, Link-Local gesperrt)."""
    if cfg.kind not in KINDS:
        raise SourceError(f"Unbekannte Art: {cfg.kind}")
    _check_url(cfg.url)
    return QdrantClient(url=cfg.url, api_key=cfg.api_key or None, timeout=TIMEOUT_S, prefer_grpc=False)


def _vector_info(collection_info) -> tuple[dict[str, int], list[str]]:
    """({Vektorname: Groesse}, [Sparse-Namen]) aus get_collection."""
    params = collection_info.config.params
    vectors = params.vectors
    dense: dict[str, int] = {}
    if hasattr(vectors, "size"):
        dense[""] = int(vectors.size)
    elif isinstance(vectors, dict):
        dense = {name: int(v.size) for name, v in vectors.items()}
    sparse = list((params.sparse_vectors or {}).keys())
    return dense, sparse


def probe_source(cfg: SourceConfig, client=None, sample_vector: bool = False) -> dict:
    """Fakten zur Quelle fuer den Abgleich durch den Anleger (rechnet nichts aus, rät nichts).

    Raises:
        SourceError: nicht erreichbar oder Collection fehlt.
    """
    own = client is None
    client = client or connect(cfg)
    try:
        try:
            names = [c.name for c in client.get_collections().collections]
        except Exception as e:
            raise SourceError(f"Nicht erreichbar: {type(e).__name__}: {e}"[:300]) from None
        result: dict = {"collections": names, "reachable": True}
        if not cfg.collection:
            return result
        if cfg.collection not in names:
            raise SourceError(f"Collection „{cfg.collection}“ gibt es auf dem Server nicht")
        info = client.get_collection(cfg.collection)
        dense, sparse = _vector_info(info)
        wanted = ([cfg.dense_vector] if sample_vector else False)
        points, _ = client.scroll(cfg.collection, limit=1, with_payload=True, with_vectors=wanted)
        result.update(
            {
                "points": int(client.count(cfg.collection).count),
                "dense_vectors": dense,  # Name ("" = unbenannt) -> Groesse
                "sparse_vectors": sparse,
                "sample_payload": (points[0].payload if points else None),
            }
        )
        if sample_vector and points:
            vec = points[0].vector
            vec = vec.get(cfg.dense_vector) if isinstance(vec, dict) else vec
            result["sample_vector"] = list(vec) if isinstance(vec, (list, tuple)) else None
        return result
    except SourceError:
        raise
    except Exception as e:
        raise SourceError(f"Abfrage fehlgeschlagen: {type(e).__name__}: {e}"[:300]) from None
    finally:
        if own:
            client.close()


MIN_SIMILARITY = 0.8


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def validate_source(cfg: SourceConfig, dimension: int, client=None, embed=None) -> dict:
    """Harte Pruefung vor dem Speichern: Vektor und Dimension passen, Felder gefunden.

    Returns:
        Die Fakten von ``probe_source``.
    Raises:
        SourceError: mit der Ursache in lesbarer Form.
    """
    if not cfg.url:
        raise SourceError("Adresse fehlt")
    if not cfg.collection:
        raise SourceError("Collection fehlt")
    facts = probe_source(cfg, client, sample_vector=embed is not None)
    dense = facts["dense_vectors"]
    if cfg.dense_vector not in dense:
        known = ", ".join(repr(n) for n in dense) or "keine"
        raise SourceError(f"Vektor {cfg.dense_vector!r} gibt es in der Collection nicht (vorhanden: {known})")
    if dense[cfg.dense_vector] != dimension:
        raise SourceError(
            f"Das Embedding-Modell liefert {dimension} Dimensionen, der Vektor der Quelle hat "
            f"{dense[cfg.dense_vector]}. Es muss das Modell sein, mit dem die Quelle aufgebaut wurde."
        )
    if cfg.sparse_vector and cfg.sparse_vector not in facts["sparse_vectors"]:
        raise SourceError(
            f"Sparse-Vektor {cfg.sparse_vector!r} gibt es nicht (vorhanden: {', '.join(facts['sparse_vectors']) or 'keine'})"
        )
    sample = facts.get("sample_payload")
    if sample is not None and cfg.fields["text"] not in sample:
        raise SourceError(
            f"Das Textfeld {cfg.fields['text']!r} steht nicht im Payload (vorhanden: {', '.join(sample) or 'keine'})"
        )
    if facts["points"] == 0:
        raise SourceError("Die Collection ist leer")
    # Gleiche Dimension heisst nicht gleiches Modell: den Text eines Beispielpunkts mit dem
    # angegebenen Modell einbetten und mit dem gespeicherten Vektor vergleichen.
    stored = facts.pop("sample_vector", None)
    if embed is not None and stored and sample:
        text = sample.get(cfg.fields["text"])
        if isinstance(text, str) and text.strip():
            similarity = _cosine(list(embed(text)), stored)
            facts["model_match"] = round(similarity, 3)
            if similarity < MIN_SIMILARITY:
                raise SourceError(
                    f"Das Embedding-Modell passt nicht zu den Vektoren der Quelle (Übereinstimmung "
                    f"{similarity:.2f} bei einem Beispieltext, erwartet über {MIN_SIMILARITY}). "
                    "Bitte das Modell angeben, mit dem die Quelle aufgebaut wurde."
                )
    return facts


def normalize_payload(payload: dict, cfg: SourceConfig) -> dict:
    """Uebersetzt die Felder der Quelle in die Namen, die die Pipeline erwartet."""
    out = dict(payload)
    f = cfg.fields
    for ours, theirs in (
        ("page_content", f["text"]),
        ("filename", f["filename"]),
        ("title", f["title"]),
        ("headers", f["headers"]),
        ("page_start", f["page_start"]),
        ("page_end", f["page_end"]),
        ("chunk_index", f["chunk_index"]),
        ("file_group_id", f["group"]),
    ):
        if theirs in payload:
            out[ours] = payload[theirs]
    return out


def layout_for(cfg: SourceConfig) -> dict:
    """Aufbau der Quelle fuer ``pipeline.run(layout=...)``."""
    return {
        "dense_name": cfg.dense_vector,
        "sparse_name": cfg.sparse_vector or None,
        "normalize": lambda payload: normalize_payload(payload, cfg),
        "neighbors": cfg.uses_default_neighbor_fields,
    }
