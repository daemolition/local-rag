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
Modell-Registry fuer Embedding und Reranking.

Ein Modell wird durch eine ``ModelSpec`` beschrieben und von hier geladen, gecacht und auf
Wunsch im Hintergrund vorgewaermt ("er muss das dann eben laden"):

- ``hf``        HuggingFace-Modell lokal ueber sentence-transformers (beliebige Modell-ID,
                z. B. ``BAAI/bge-m3``, ``BAAI/bge-reranker-v2-m3``). Download beim ersten Mal.
- ``endpoint``  OpenAI-kompatibler ``/embeddings`` bzw. ``/rerank``-Endpunkt einer Connection
                (vLLM, TEI, Infinity, LiteLLM) mit Base-URL und Key.
- ``fastembed`` ONNX-Modelle aus der fastembed-Liste. Nur noch fuer bestehende Installationen,
                deren Vektoren mit diesem Modell entstanden sind.

Die Dimension eines Embedders wird per Probe-Embedding ermittelt (nie eingetippt).
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from logging import getLogger

import requests

from app.utils.device import onnx_providers, torch_device

logger = getLogger(__name__)

SOURCES = ("hf", "endpoint", "fastembed")
DEFAULT_EMBEDDING = {"source": "hf", "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}
DEFAULT_RERANKER = {"source": "hf", "model": "BAAI/bge-reranker-base"}
EMBED_BATCH = 32
HTTP_TIMEOUT = 120
# Nach einem gescheiterten Ladeversuch wird so lange nicht erneut versucht (Download/Netz).
RETRY_AFTER_SECONDS = 60


class ModelLoadError(Exception):
    """Modell konnte nicht geladen oder erreicht werden (Meldung ist fuer Nutzer lesbar)."""


@dataclass(frozen=True)
class ModelSpec:
    source: str
    model: str
    connection_id: int | None = None

    def __post_init__(self):
        if self.source not in SOURCES:
            raise ValueError(f"Unbekannte Quelle: {self.source!r}")
        if not (self.model or "").strip():
            raise ValueError("Modell fehlt")
        if self.source == "endpoint" and not self.connection_id:
            raise ValueError("Für einen Endpoint wird eine Connection gebraucht")

    @property
    def key(self) -> str:
        return f"{self.source}:{self.connection_id or ''}:{self.model}"

    def to_dict(self) -> dict:
        d = {"source": self.source, "model": self.model}
        if self.connection_id:
            d["connection_id"] = self.connection_id
        return d

    @classmethod
    def from_dict(cls, data: dict | str | None) -> "ModelSpec":
        if isinstance(data, str):
            data = json.loads(data)
        data = data or {}
        cid = data.get("connection_id")
        return cls(
            source=data.get("source", ""),
            model=(data.get("model") or "").strip(),
            connection_id=int(cid) if cid else None,
        )


# --------------------------------------------------------------------------
# Embedder
# --------------------------------------------------------------------------


class _Embedder:
    """Gemeinsame Basis: ``embed_query``, ``embed_documents``, ``dimension``."""

    spec: ModelSpec
    _dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("Dimensionstest"))
        return self._dimension

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HFEmbedder(_Embedder):
    def __init__(self, spec: ModelSpec):
        from sentence_transformers import SentenceTransformer

        self.spec = spec
        self._lock = threading.Lock()
        self._model = SentenceTransformer(spec.model, device=torch_device())
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        dim = get_dim()
        self._dimension = int(dim) if dim else None

    def _encode(self, texts: list[str], query: bool) -> list[list[float]]:
        # encode_query/encode_document wenden die Prompts des Modells an (z. B. "query: " bei e5).
        name = "encode_query" if query else "encode_document"
        fn = getattr(self._model, name, None) or self._model.encode  # aeltere Versionen: nur encode
        with self._lock:  # Inferenz serialisieren (gunicorn --threads 4)
            vectors = fn(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vectors]

    def embed_query(self, text):
        return self._encode([text], query=True)[0]

    def embed_documents(self, texts):
        return self._encode(texts, query=False) if texts else []


class FastEmbedEmbedder(_Embedder):
    def __init__(self, spec: ModelSpec):
        from langchain_community.embeddings import FastEmbedEmbeddings

        self.spec = spec
        self._model = FastEmbedEmbeddings(model_name=spec.model)

    def embed_query(self, text):
        return list(self._model.embed_query(text))

    def embed_documents(self, texts):
        return [list(v) for v in self._model.embed_documents(texts)] if texts else []


def _connection(spec: ModelSpec) -> dict:
    from app import connections as store
    from app.llm.registry import RemoteModelsError, _reject_link_local

    conn = store.get_connection(spec.connection_id, with_key=True)
    if not conn:
        raise ModelLoadError("Die Connection des Modells existiert nicht mehr")
    if not conn["enabled"]:
        raise ModelLoadError(f"Connection „{conn['name']}“ ist deaktiviert")
    try:
        _reject_link_local(conn["base_url"])
    except RemoteModelsError as e:
        raise ModelLoadError(str(e)) from None
    return conn


def _post(url: str, key: str, payload: dict, what: str) -> requests.Response:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=False
            )
        except requests.exceptions.RequestException as e:
            last = e
        else:
            if 300 <= resp.status_code < 400:
                raise ModelLoadError(f"{what}: Weiterleitung wird nicht verfolgt (HTTP {resp.status_code})")
            if resp.status_code in (401, 403):
                raise ModelLoadError(f"{what}: Zugriff verweigert (HTTP {resp.status_code}), API-Key prüfen")
            if resp.status_code < 500:
                return resp
            last = RuntimeError(f"HTTP {resp.status_code}")
        time.sleep(0.5 * (attempt + 1))
    raise ModelLoadError(f"{what}: {last}")


class EndpointEmbedder(_Embedder):
    def __init__(self, spec: ModelSpec):
        self.spec = spec
        conn = _connection(spec)
        self._url = f"{conn['base_url']}/embeddings"
        self._key = conn["api_key"]
        self.dimension  # Probe: Erreichbarkeit, Modellname und Dimension pruefen  # noqa: B018

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            resp = _post(self._url, self._key, {"model": self.spec.model, "input": batch}, "Embedding-Endpoint")
            if resp.status_code != 200:
                raise ModelLoadError(f"Embedding-Endpoint: HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                rows = sorted(resp.json()["data"], key=lambda r: r["index"])
                vectors = [list(map(float, r["embedding"])) for r in rows]
            except (KeyError, ValueError, TypeError):
                raise ModelLoadError("Embedding-Endpoint: unerwartete Antwort (kein OpenAI-Format)") from None
            if len(vectors) != len(batch):
                raise ModelLoadError("Embedding-Endpoint: Anzahl der Vektoren passt nicht zur Anfrage")
            out.extend(vectors)
        return out

    def embed_query(self, text):
        return self._embed([text])[0]

    def embed_documents(self, texts):
        return self._embed(texts) if texts else []


# --------------------------------------------------------------------------
# Reranker
# --------------------------------------------------------------------------

MAX_RERANK_CHARS = 2000


class _Reranker:
    spec: ModelSpec

    def score(self, query: str, texts: list[str]) -> list[float]:
        raise NotImplementedError


class HFReranker(_Reranker):
    def __init__(self, spec: ModelSpec):
        from sentence_transformers import CrossEncoder

        self.spec = spec
        self._lock = threading.Lock()
        self._model = CrossEncoder(spec.model, device=torch_device())

    def score(self, query, texts):
        if not texts:
            return []
        pairs = [(query, t[:MAX_RERANK_CHARS]) for t in texts]
        with self._lock:
            return [float(s) for s in self._model.predict(pairs, show_progress_bar=False)]


class FastEmbedReranker(_Reranker):
    def __init__(self, spec: ModelSpec):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.spec = spec
        self._lock = threading.Lock()
        providers = onnx_providers()
        self._model = (
            TextCrossEncoder(model_name=spec.model, providers=providers)
            if providers
            else TextCrossEncoder(model_name=spec.model)
        )

    def score(self, query, texts):
        if not texts:
            return []
        with self._lock:
            return [float(s) for s in self._model.rerank(query, [t[:MAX_RERANK_CHARS] for t in texts])]


class EndpointReranker(_Reranker):
    """``POST {base_url}/rerank`` (Jina/vLLM/TEI-Format)."""

    def __init__(self, spec: ModelSpec):
        self.spec = spec
        conn = _connection(spec)
        self._base = conn["base_url"]
        self._key = conn["api_key"]
        self.score("Test", ["Test"])  # Probe: Erreichbarkeit und Modellname

    def _urls(self) -> list[str]:
        urls = [f"{self._base}/rerank"]
        if self._base.endswith("/v1"):  # TEI & Co. bieten /rerank ohne /v1
            urls.append(f"{self._base[:-3]}/rerank")
        return urls

    def score(self, query, texts):
        if not texts:
            return []
        payload = {
            "model": self.spec.model,
            "query": query,
            "documents": [t[:MAX_RERANK_CHARS] for t in texts],
        }
        resp = None
        for url in self._urls():
            resp = _post(url, self._key, payload, "Rerank-Endpoint")
            if resp.status_code != 404:
                break
        if resp is None or resp.status_code != 200:
            raise ModelLoadError(f"Rerank-Endpoint: HTTP {getattr(resp, 'status_code', '?')}: {getattr(resp, 'text', '')[:200]}")
        try:
            body = resp.json()
            rows = body["results"] if isinstance(body, dict) else body
            scores = [None] * len(texts)
            for row in rows:
                scores[int(row["index"])] = float(row.get("relevance_score", row.get("score")))
        except (KeyError, ValueError, TypeError, IndexError):
            raise ModelLoadError("Rerank-Endpoint: unerwartete Antwort") from None
        if any(s is None for s in scores):
            raise ModelLoadError("Rerank-Endpoint: nicht zu jedem Text kam ein Score zurück")
        return scores


# --------------------------------------------------------------------------
# Cache und Status
# --------------------------------------------------------------------------

_EMBEDDER_CLASSES = {"hf": HFEmbedder, "fastembed": FastEmbedEmbedder, "endpoint": EndpointEmbedder}
_RERANKER_CLASSES = {"hf": HFReranker, "fastembed": FastEmbedReranker, "endpoint": EndpointReranker}

_lock = threading.RLock()
_loaded: dict[tuple[str, str], object] = {}
_status: dict[tuple[str, str], dict] = {}
_key_locks: dict[tuple[str, str], threading.Lock] = {}


def _load(kind: str, spec: ModelSpec):
    classes = _EMBEDDER_CLASSES if kind == "embedding" else _RERANKER_CLASSES
    key = (kind, spec.key)
    with _lock:
        if key in _loaded:
            return _loaded[key]
        key_lock = _key_locks.setdefault(key, threading.Lock())
    with key_lock:  # ein Ladevorgang pro Modell
        with _lock:
            if key in _loaded:
                return _loaded[key]
            prev = _status.get(key)
            if prev and prev.get("state") == "error" and time.time() - prev["at"] < RETRY_AFTER_SECONDS:
                raise ModelLoadError(prev["error"])
            _status[key] = {"state": "loading", "at": time.time(), "spec": spec.to_dict()}
        started = time.time()
        try:
            obj = classes[spec.source](spec)
            dimension = obj.dimension if kind == "embedding" else None
        except ModelLoadError as e:
            _fail(key, spec, str(e))
            raise
        except Exception as e:
            message = f"{type(e).__name__}: {e}"[:300]
            _fail(key, spec, f"Modell „{spec.model}“ konnte nicht geladen werden: {message}")
            raise ModelLoadError(_status[key]["error"]) from e
        with _lock:
            _loaded[key] = obj
            _status[key] = {
                "state": "ready", "at": time.time(), "spec": spec.to_dict(),
                "seconds": round(time.time() - started, 1), "dimension": dimension,
            }
        logger.info(f"Modell geladen: {spec.key} ({_status[key]['seconds']} s)")
        return obj


def _fail(key, spec, message):
    with _lock:
        _status[key] = {"state": "error", "at": time.time(), "spec": spec.to_dict(), "error": message}
    logger.warning(message)


def get_embedder(spec: ModelSpec) -> _Embedder:
    return _load("embedding", spec)


def get_reranker(spec: ModelSpec) -> _Reranker:
    return _load("reranker", spec)


def load_in_background(kind: str, spec: ModelSpec) -> None:
    """Laedt (und laedt ggf. herunter) das Modell, ohne den Aufrufer warten zu lassen."""
    def run():
        try:
            _load(kind, spec)
        except ModelLoadError:
            pass  # steht im Status

    threading.Thread(target=run, name=f"load-{kind}", daemon=True).start()


def status(kind: str, spec: ModelSpec | None) -> dict:
    """``{"state": "ready"|"loading"|"error"|"not_loaded", ...}`` fuer die Anzeige."""
    if spec is None:
        return {"state": "not_loaded"}
    with _lock:
        s = _status.get((kind, spec.key))
    return dict(s) if s else {"state": "not_loaded", "spec": spec.to_dict()}


def forget(kind: str, spec: ModelSpec) -> None:
    """Entlaedt ein Modell (Speicher freigeben, z. B. nach einem Wechsel)."""
    with _lock:
        _loaded.pop((kind, spec.key), None)
        _status.pop((kind, spec.key), None)


def reset_for_tests() -> None:
    with _lock:
        _loaded.clear()
        _status.clear()
        _key_locks.clear()


# --------------------------------------------------------------------------
# Signatur und Kollektionsnamen
# --------------------------------------------------------------------------


def index_signature(embedding: ModelSpec | dict, chunk_size: int, chunk_overlap: int, *versions: int) -> str:
    """Kennzeichnet, womit ein Index erzeugt wurde. Weicht sie von der aktuellen
    Konfiguration ab, gilt der Index als veraltet (Neu indexieren empfohlen)."""
    spec = embedding if isinstance(embedding, ModelSpec) else ModelSpec.from_dict(embedding)
    raw = json.dumps([spec.key, chunk_size, chunk_overlap, *versions])
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def uploads_collection(spec: ModelSpec) -> str:
    """Collection der Chat-Anhaenge je Embedding-Modell (Vektoren verschiedener Modelle mischen nicht)."""
    return f"user_uploads_{hashlib.sha256(spec.key.encode()).hexdigest()[:8]}"
