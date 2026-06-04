from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
import math
import os
import re
from typing import Iterable

from app.models import NormalizedReview


DEFAULT_SENTENCE_TRANSFORMER_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
SENTENCE_TRANSFORMER_MODEL_NAME = "local-sentence-transformer-review-embeddings"
TFIDF_EMBEDDING_MODEL_NAME = "local-tfidf-cosine-review-embeddings"
TOKEN_OVERLAP_MODEL_NAME = "local-token-overlap-review-embeddings"
FALLBACK_MODEL_VERSION = "2026.07.demo-fallback"
DEFAULT_SIMILARITY_THRESHOLD = 0.78
DEFAULT_MIN_CLUSTER_SIZE = 2


@dataclass(frozen=True)
class ReviewSemanticRecord:
    id: int
    title: str | None
    body: str
    source_code: str
    source_name: str
    review_date: str | None
    category_code: str
    department_code: str

    @property
    def text(self) -> str:
        return " ".join(part for part in [self.title, self.body] if part).strip()


@dataclass(frozen=True)
class SemanticDuplicatePair:
    review_id: int
    matched_review_id: int
    similarity: float
    category_code: str
    department_code: str


@dataclass(frozen=True)
class SemanticIssueCluster:
    cluster_id: str
    size: int
    representative_review_id: int
    representative_text: str
    category_code: str
    department_code: str
    source_mix: dict[str, int]
    review_ids: list[int]
    average_similarity: float


@dataclass(frozen=True)
class SemanticAnalysisResult:
    embedding_strategy: str
    embedding_model_name: str
    embedding_model_version: str
    embedding_fallback_note: str
    similarity_threshold: float
    min_cluster_size: int
    near_duplicate_pairs: list[SemanticDuplicatePair]
    clusters: list[SemanticIssueCluster]


@dataclass(frozen=True)
class SimilarityRuntimeMetadata:
    embedding_strategy: str
    embedding_model_name: str
    embedding_model_version: str
    embedding_fallback_note: str


@dataclass(frozen=True)
class SimilarityComputation:
    metadata: SimilarityRuntimeMetadata
    similarities: dict[tuple[int, int], float]


class LocalSemanticSimilarityAnalyzer:
    def __init__(self) -> None:
        self.model_id = os.getenv("SEMANTIC_SIMILARITY_MODEL_ID", DEFAULT_SENTENCE_TRANSFORMER_MODEL_ID)
        self.model_revision = os.getenv("SEMANTIC_SIMILARITY_MODEL_REVISION")
        self._model = None
        self._unavailable_reason: str | None = None
        try:
            self._model = _load_sentence_transformer(
                model_id=self.model_id,
                revision=self.model_revision,
            )
        except Exception as exc:  # pragma: no cover - exercised through monkeypatched tests
            self._unavailable_reason = f"{type(exc).__name__}: {exc}"

    def analyze(self, texts: list[str]) -> SimilarityComputation:
        if self._model is not None:
            try:
                return SimilarityComputation(
                    metadata=SimilarityRuntimeMetadata(
                        embedding_strategy="local_sentence_transformer",
                        embedding_model_name=SENTENCE_TRANSFORMER_MODEL_NAME,
                        embedding_model_version=(
                            self.model_revision
                            or _sentence_transformer_version(self._model)
                            or self.model_id
                        ),
                        embedding_fallback_note=(
                            "Local sentence-transformer embeddings are active. TF-IDF cosine similarity and "
                            "token-overlap fallback remain available when local dependencies or model artifacts "
                            "are unavailable."
                        ),
                    ),
                    similarities=_sentence_embedding_similarities(texts, self._model),
                )
            except Exception as exc:  # pragma: no cover - hard to trigger without monkeypatching
                self._unavailable_reason = f"{type(exc).__name__}: {exc}"

        return _fallback_similarity_computation(texts, sentence_transformer_reason=self._unavailable_reason)

    def metadata(self) -> SimilarityRuntimeMetadata:
        if self._model is not None:
            return SimilarityRuntimeMetadata(
                embedding_strategy="local_sentence_transformer",
                embedding_model_name=SENTENCE_TRANSFORMER_MODEL_NAME,
                embedding_model_version=self.model_revision or _sentence_transformer_version(self._model) or self.model_id,
                embedding_fallback_note=(
                    "Local sentence-transformer embeddings are active. TF-IDF cosine similarity and token-overlap "
                    "fallback remain available when local dependencies or model artifacts are unavailable."
                ),
            )
        return _fallback_similarity_computation(
            ["semantic placeholder one", "semantic placeholder two"],
            sentence_transformer_reason=self._unavailable_reason,
        ).metadata


def analyze_semantic_similarity(
    reviews: Iterable[NormalizedReview],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
) -> SemanticAnalysisResult:
    records = [_semantic_record(review) for review in reviews if review.body.strip()]
    runtime = get_semantic_similarity_analyzer()
    if len(records) < 2:
        return _empty_result(similarity_threshold, min_cluster_size, runtime.metadata())

    computation = runtime.analyze([record.text for record in records])
    similarities = computation.similarities
    pairs = [
        SemanticDuplicatePair(
            review_id=records[left].id,
            matched_review_id=records[right].id,
            similarity=round(score, 3),
            category_code=_dominant_value([records[left].category_code, records[right].category_code]),
            department_code=_dominant_value([records[left].department_code, records[right].department_code]),
        )
        for (left, right), score in similarities.items()
        if score >= similarity_threshold
    ]
    clusters = _build_clusters(records, similarities, similarity_threshold, min_cluster_size)
    return SemanticAnalysisResult(
        embedding_strategy=computation.metadata.embedding_strategy,
        embedding_model_name=computation.metadata.embedding_model_name,
        embedding_model_version=computation.metadata.embedding_model_version,
        embedding_fallback_note=computation.metadata.embedding_fallback_note,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        near_duplicate_pairs=sorted(pairs, key=lambda pair: pair.similarity, reverse=True),
        clusters=clusters,
    )


def _semantic_record(review: NormalizedReview) -> ReviewSemanticRecord:
    category_code = review.issue_category_code
    department_code = review.department_code
    if review.analysis is not None:
        primary_prediction = next(
            (prediction for prediction in review.analysis.issue_category_predictions if prediction.is_primary),
            None,
        )
        category_code = primary_prediction.category_code if primary_prediction is not None else review.analysis.issue_category_code
        department_code = primary_prediction.department_code if primary_prediction is not None else review.analysis.department_code

    return ReviewSemanticRecord(
        id=review.id,
        title=review.title,
        body=review.body,
        source_code=review.source_code,
        source_name=review.source_name,
        review_date=review.review_date.isoformat() if review.review_date is not None else None,
        category_code=category_code,
        department_code=department_code,
    )


def _fallback_similarity_computation(
    texts: list[str],
    *,
    sentence_transformer_reason: str | None,
) -> SimilarityComputation:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            stop_words="english",
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
        scores = cosine_similarity(matrix)
        return SimilarityComputation(
            metadata=SimilarityRuntimeMetadata(
                embedding_strategy="tfidf_cosine_fallback",
                embedding_model_name=TFIDF_EMBEDDING_MODEL_NAME,
                embedding_model_version=FALLBACK_MODEL_VERSION,
                embedding_fallback_note=(
                    "Local scikit-learn TF-IDF cosine fallback is active because sentence-transformers "
                    f"dependencies or local model artifacts are unavailable: {sentence_transformer_reason or 'not installed locally'}."
                ),
            ),
            similarities={
                (left, right): float(scores[left, right])
                for left in range(len(texts))
                for right in range(left + 1, len(texts))
            },
        )
    except (ImportError, ValueError) as exc:
        token_sets = [_tokenize(text) for text in texts]
        return SimilarityComputation(
            metadata=SimilarityRuntimeMetadata(
                embedding_strategy="token_overlap_fallback",
                embedding_model_name=TOKEN_OVERLAP_MODEL_NAME,
                embedding_model_version=FALLBACK_MODEL_VERSION,
                embedding_fallback_note=(
                    "Token-overlap fallback is active because scikit-learn TF-IDF and sentence-transformers "
                    "runtime support are unavailable"
                    f"{_format_sentence_transformer_reason(sentence_transformer_reason)}; "
                    f"scikit-learn failure was {type(exc).__name__}: {exc}."
                ),
            ),
            similarities={
                (left, right): _jaccard_similarity(token_sets[left], token_sets[right])
                for left in range(len(texts))
                for right in range(left + 1, len(texts))
            },
        )


def _load_sentence_transformer(*, model_id: str, revision: str | None):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model_name_or_path=model_id,
        revision=revision,
        local_files_only=True,
    )


def _sentence_transformer_version(model) -> str | None:
    for attribute in ("revision", "_revision"):
        value = getattr(model, attribute, None)
        if value:
            return str(value)
    model_card_data = getattr(model, "model_card_data", None)
    base_model = getattr(model_card_data, "base_model", None) if model_card_data is not None else None
    if base_model:
        return str(base_model)
    return None


def _sentence_embedding_similarities(texts: list[str], model) -> dict[tuple[int, int], float]:
    embeddings = model.encode(texts, normalize_embeddings=True)
    rows = embeddings.tolist() if hasattr(embeddings, "tolist") else list(embeddings)
    normalized_rows = [list(row) for row in rows]
    return {
        (left, right): round(_dot_product(normalized_rows[left], normalized_rows[right]), 6)
        for left in range(len(normalized_rows))
        for right in range(left + 1, len(normalized_rows))
    }


def _dot_product(left: list[float], right: list[float]) -> float:
    return max(min(sum(a * b for a, b in zip(left, right)), 1.0), -1.0)


def _format_sentence_transformer_reason(reason: str | None) -> str:
    if reason is None:
        return ""
    return f" ({reason})"


def _build_clusters(
    records: list[ReviewSemanticRecord],
    similarities: dict[tuple[int, int], float],
    threshold: float,
    min_cluster_size: int,
) -> list[SemanticIssueCluster]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for (left, right), score in similarities.items():
        if score >= threshold:
            adjacency[left].add(right)
            adjacency[right].add(left)

    visited: set[int] = set()
    clusters: list[SemanticIssueCluster] = []
    for start in sorted(adjacency):
        if start in visited:
            continue
        component = _connected_component(start, adjacency, visited)
        if len(component) < min_cluster_size:
            continue
        component_records = [records[index] for index in sorted(component)]
        representative_index = _representative_index(component, similarities)
        representative = records[representative_index]
        pair_scores = [
            similarities[tuple(sorted((left, right)))]
            for left in component
            for right in component
            if left < right and tuple(sorted((left, right))) in similarities
        ]
        clusters.append(
            SemanticIssueCluster(
                cluster_id=f"semantic-{len(clusters) + 1}",
                size=len(component_records),
                representative_review_id=representative.id,
                representative_text=representative.text[:240],
                category_code=_dominant_value(record.category_code for record in component_records),
                department_code=_dominant_value(record.department_code for record in component_records),
                source_mix=dict(sorted(Counter(record.source_code for record in component_records).items())),
                review_ids=[record.id for record in component_records],
                average_similarity=round(sum(pair_scores) / len(pair_scores), 3) if pair_scores else 0.0,
            )
        )

    return sorted(clusters, key=lambda cluster: (cluster.size, cluster.average_similarity), reverse=True)


def _connected_component(start: int, adjacency: dict[int, set[int]], visited: set[int]) -> set[int]:
    component: set[int] = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        current = queue.popleft()
        component.add(current)
        for neighbor in sorted(adjacency[current]):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return component


def _representative_index(component: set[int], similarities: dict[tuple[int, int], float]) -> int:
    return max(
        component,
        key=lambda index: (
            sum(
                similarities.get(tuple(sorted((index, other))), 0.0)
                for other in component
                if other != index
            )
            / max(len(component) - 1, 1),
            -index,
        ),
    )


def _dominant_value(values: Iterable[str]) -> str:
    counts = Counter(values)
    return counts.most_common(1)[0][0]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z-]+", text.lower()))


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _empty_result(
    similarity_threshold: float,
    min_cluster_size: int,
    metadata: SimilarityRuntimeMetadata,
) -> SemanticAnalysisResult:
    return SemanticAnalysisResult(
        embedding_strategy=metadata.embedding_strategy,
        embedding_model_name=metadata.embedding_model_name,
        embedding_model_version=metadata.embedding_model_version,
        embedding_fallback_note=metadata.embedding_fallback_note,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        near_duplicate_pairs=[],
        clusters=[],
    )


@lru_cache(maxsize=1)
def get_semantic_similarity_analyzer() -> LocalSemanticSimilarityAnalyzer:
    return LocalSemanticSimilarityAnalyzer()
