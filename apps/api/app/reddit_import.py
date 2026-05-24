from sqlalchemy.orm import Session

from app.ingestion import run_payload_ingestion


REDDIT_SOURCE_CODE = "reddit_social_listening"
REDDIT_CONNECTOR_KEY = "reddit_social_listening"

REDDIT_SOCIAL_LISTENING_RECORDS = [
    {
        "external_review_id": "reddit-t3-kingsbury-001",
        "source_code": REDDIT_SOURCE_CODE,
        "source_name": "Reddit Social Listening",
        "source_type": "social_listening",
        "source_url": "https://www.reddit.com/r/srilanka/comments/kingsbury001/",
        "reviewer_name": "u/travel_lk",
        "review_date": "2026-06-18T12:40:00+00:00",
        "rating": None,
        "language": "en",
        "title": "Kingsbury check-in queue before a weekend event",
        "body": "Saw several people discussing a slow check-in queue at The Kingsbury before a weekend event.",
        "sentiment_label": "negative",
        "sentiment_score": -0.41,
        "issue_category_code": "booking_checkin",
        "severity": "medium",
        "department_code": "front_office",
    },
    {
        "external_review_id": "reddit-t1-kingsbury-002",
        "source_code": REDDIT_SOURCE_CODE,
        "source_name": "Reddit Social Listening",
        "source_type": "social_listening",
        "source_url": "https://www.reddit.com/r/srilanka/comments/kingsbury002/comment/kingsbury002/",
        "reviewer_name": "u/colombo_foodie",
        "review_date": "2026-06-19T17:05:00+00:00",
        "rating": None,
        "language": "en",
        "title": "Reddit mention about event noise",
        "body": "A Reddit thread mentioned that music from a banquet at The Kingsbury was audible from rooms late at night.",
        "sentiment_label": "negative",
        "sentiment_score": -0.36,
        "issue_category_code": "noise_events",
        "severity": "medium",
        "department_code": "guest_relations",
    },
]


def run_reddit_social_listening_ingestion(session: Session):
    return run_payload_ingestion(
        session,
        source_code=REDDIT_SOURCE_CODE,
        connector_key=REDDIT_CONNECTOR_KEY,
        payloads=REDDIT_SOCIAL_LISTENING_RECORDS,
    )
