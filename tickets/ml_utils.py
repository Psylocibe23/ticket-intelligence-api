"""
Utility per il modello di ML:

- training (TF-IDF + Logistic Regression) sulla tabella Ticket
- salvataggio/caricamento del modello
- predizione categoria e ricerca ticket simili
"""
from pathlib import Path

from django.conf import settings

from .models import Ticket
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
import joblib


MODEL_DIR = Path(settings.BASE_DIR) / "ml" / "artifacts"
MODEL_PATH = MODEL_DIR / "ticket_classifier.joblib"

# Semplice cache in memoria del modello già caricato
_cached_model = None


def _build_text(title, description) -> str:
    """
    Costruisce il testo di input per il modello a partire da title + description,
    gestendo eventuali None e spazi.
    """
    title = (title or "").strip()
    desc = (description or "").strip()
    if title and desc:
        return f"{title} {desc}"
    return title or desc


def get_training_data():
    """
    Estrae dai Ticket solo quelli con category valorizzata,
    e costruisce (texts, labels) per il training.
    """
    qs = Ticket.objects.exclude(category__isnull=True).exclude(category="")

    texts = []
    labels = []
    for t in qs:
        texts.append(_build_text(t.title, t.description))
        labels.append(t.category)

    return texts, labels


def train_model():
    """
    Allena un modello TF-IDF + Logistic Regression e lo salva su disco.
    Ritorna alcune info riassuntive per l'endpoint /analytics.
    """
    texts, labels = get_training_data()
    # nessun dato o una sola classe -> non ha senso allenare
    if not texts or len(set(labels)) < 2:
        return None

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            # class_weight="balanced" aiuta se le categorie sono sbilanciate
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    pipeline.fit(texts, labels)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    global _cached_model
    _cached_model = pipeline

    return {
        "n_samples": len(texts),
        "n_classes": len(set(labels)),
        "classes": sorted(set(labels)),
        "model_path": str(MODEL_PATH),
    }


def load_model():
    """
    Carica il modello da cache se disponibile, altrimenti da disco.
    Se il file non esiste, ritorna None.
    """
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    if not MODEL_PATH.exists():
        return None
    _cached_model = joblib.load(MODEL_PATH)
    return _cached_model


def predict_category_for_ticket(ticket: Ticket):
    """
    Predice la categoria di un singolo ticket usando il modello allenato.
    Se il modello non esiste, ritorna None.
    """
    model = load_model()
    if model is None:
        return None

    text = _build_text(ticket.title, ticket.description)
    proba = getattr(model, "predict_proba", None)
    if proba:
        probs = proba([text])[0]
        classes = model.classes_
        max_idx = probs.argmax()
        return {
            "category": classes[max_idx],
            "confidence": float(probs[max_idx]),
        }
    else:
        # fallback se predict_proba non supportata
        pred = model.predict([text])[0]
        return {"category": pred, "confidence": None}


def get_similar_tickets(ticket: Ticket, top_k=5, max_corpus=500):
    """
    Trova i ticket più simili (in base a TF-IDF + cosine similarity) rispetto al ticket passato.
    """
    model = load_model()
    if model is None:
        return []

    tfidf = model.named_steps["tfidf"]

    # corpus: ultimi max_corpus ticket diversi da quello target
    qs = (
        Ticket.objects.exclude(id=ticket.id)
        .order_by("-created_at")[:max_corpus]
    )

    corpus = [_build_text(t.title, t.description) for t in qs]
    if not corpus:
        return []

    query_vec = tfidf.transform([_build_text(ticket.title, ticket.description)])
    corpus_vec = tfidf.transform(corpus)

    sims = cosine_similarity(query_vec, corpus_vec)[0]
    scored = list(zip(qs, sims))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]

    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "category": t.category,
            "similarity": float(score),
        }
        for (t, score) in top
    ]
