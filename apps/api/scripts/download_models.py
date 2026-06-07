"""Download and cache all Hugging Face models required by the app.

Run once after `npm run api:install:nlp` so models are available locally
for `local_files_only=True` loads throughout the app.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _download(repo_id: str, model_type: str) -> None:
    print(f"Downloading {repo_id} ({model_type}) ...")
    if model_type == "sentence_transformer":
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(repo_id)
    elif model_type == "seq2seq":
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        AutoTokenizer.from_pretrained(repo_id)
        AutoModelForSeq2SeqLM.from_pretrained(repo_id)
    elif model_type == "classification":
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        AutoTokenizer.from_pretrained(repo_id)
        AutoModelForSequenceClassification.from_pretrained(repo_id)
    elif model_type == "config":
        from transformers import AutoConfig
        AutoConfig.from_pretrained(repo_id)
    print(f"  done")


def main() -> None:
    models = [
        ("nlptown/bert-base-multilingual-uncased-sentiment", "classification"),
        ("facebook/bart-large-mnli", "classification"),
        ("sentence-transformers/all-MiniLM-L6-v2", "sentence_transformer"),
        ("google/flan-t5-base", "seq2seq"),
        ("google/flan-t5-base", "config"),
    ]
    for repo_id, model_type in models:
        _download(repo_id, model_type)
    print("\nAll models downloaded and cached.")


if __name__ == "__main__":
    main()
