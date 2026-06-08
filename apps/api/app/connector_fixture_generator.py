from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import random
import re
import sys
from typing import Any
from urllib import request


DEFAULT_MODEL = "llama3.1:latest"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TOTAL_REVIEWS = 2000
DEFAULT_DATE_WINDOW_START = datetime(2025, 6, 5, 0, 0, tzinfo=UTC)
DEFAULT_DATE_WINDOW_END = datetime(2026, 6, 5, 23, 59, 59, tzinfo=UTC)
DEFAULT_OUTPUT_BASE = Path("apps/api/data/generated-fixtures")
PLATFORMS = ("google_business_profile", "booking_com", "tripadvisor")
ANALYSIS_FIELD_NAMES = {
    "analysis",
    "mock_analysis",
    "sentiment",
    "sentiment_label",
    "sentiment_score",
    "issue_category",
    "issue_category_code",
    "department",
    "department_code",
    "reputation_risk",
    "reputation_risk_label",
    "reputation_risk_score",
    "precomputed_analysis",
}

STAR_RATING_NAMES = {
    1: "ONE",
    2: "TWO",
    3: "THREE",
    4: "FOUR",
    5: "FIVE",
}

# --------------------------------------------------------------------------------------------
# Scenario library.
#
# The old generator only had 6 vague themes, so every review was generic ("AC not working")
# and the downstream issue pipeline could never produce pinpointed issues. We instead drive
# generation from CONCRETE incidents: each scenario template carries placeholders that get
# filled with specific facts (room/floor/item/amount/time). Putting the specifics in the
# scenario - not relying on the model to invent them - makes even a small local model produce
# specific, varied reviews.
#
# Recurring scenarios (high weight) appear many times with DIFFERENT specifics -> the pipeline
# can consolidate them into one issue while still citing the specifics. Sporadic severe
# scenarios (low weight) appear occasionally and stay as their own pinpointed issue.
# --------------------------------------------------------------------------------------------

_FOOD_ITEMS = (
    "scrambled eggs", "pancakes", "the omelette", "string hoppers", "the fruit platter",
    "fried rice", "the chicken curry", "the morning coffee", "toast", "the pastries",
)
_FIXTURES = (
    "hair dryer", "room safe", "shower mixer", "electric kettle", "minibar fridge",
    "TV remote", "bathroom door lock", "reading lamp", "air conditioner remote", "shower head",
)
_STAFF_ROLES = (
    "front desk agent", "duty manager", "housekeeping supervisor", "breakfast waiter",
    "concierge", "night receptionist", "bell desk staff",
)
_TIMES = ("7:30am", "9pm", "1am", "2am", "midnight", "6am", "11pm", "check-out", "8:15am")


def _room(rng: random.Random) -> str:
    floor = rng.randint(2, 18)
    return f"{floor}{rng.randint(1, 40):02d}"


def _fill(template: str, rng: random.Random) -> str:
    room = _room(rng)
    floor = int(room[:-2]) if len(room) >= 3 else int(room[0])
    floor_word = {1: "1st", 2: "2nd", 3: "3rd"}.get(floor, f"{floor}th")
    return template.format(
        room=room,
        floor=floor_word,
        room_type=rng.choice(ROOM_NAMES).lower(),
        temp=rng.randint(26, 31),
        nights=rng.choice(("one", "two", "three")),
        hours=rng.randint(1, 6),
        minutes=rng.randint(20, 80),
        amount=rng.randint(15, 130),
        item=rng.choice(_FOOD_ITEMS),
        fixture=rng.choice(_FIXTURES),
        staff=rng.choice(_STAFF_ROLES),
        time=rng.choice(_TIMES),
    )


# Each scenario: department (for our own reference only - NOT written into reviews), the star
# ratings it can carry, a sampling weight, and one or more fact-bearing templates.
SCENARIOS: tuple[dict[str, Any], ...] = (
    # --- Recurring operational problems (consolidate into one issue each) ---
    {"key": "ac_not_cooling", "weight": 9, "ratings": (1, 2, 3), "templates": (
        "the air conditioning in {room_type} {room} on the {floor} floor barely cooled the room, it stayed around {temp} degrees for {nights} nights",
        "AC in room {room} stopped cooling overnight and we waited {hours} hours for someone from maintenance to look at it",
        "room {room} never got cold, the air conditioner ran all night but it was still {temp} degrees when we woke up",
    )},
    {"key": "slow_checkin", "weight": 8, "ratings": (2, 3), "templates": (
        "check-in took about {minutes} minutes with only one person at reception when we arrived at {time}",
        "we queued at the front desk for roughly {minutes} minutes at {time}, the line barely moved",
    )},
    {"key": "noise", "weight": 8, "ratings": (1, 2, 3), "templates": (
        "loud music from an event downstairs kept us awake until {time} in room {room}",
        "we could hear thumping bass and shouting from a function until {time}, room {room} on the {floor} floor had no sound proofing",
        "noise from the room next door and the corridor went on past {time}, impossible to sleep",
    )},
    {"key": "breakfast_quality", "weight": 7, "ratings": (2, 3), "templates": (
        "{item} at breakfast was cold and was not refilled when it ran out during the morning rush",
        "the breakfast buffet was nearly empty by 9:30am, {item} was finished and nobody topped it up",
    )},
    {"key": "housekeeping_dirty", "weight": 7, "ratings": (1, 2, 3), "templates": (
        "room {room} was not cleaned properly, there were used towels and hair in the bathroom when we checked in",
        "the sheets in room {room} had stains and the bin had not been emptied from the previous guest",
        "housekeeping skipped room {room} on day {hours} of our stay even after we requested service",
    )},
    {"key": "plumbing", "weight": 6, "ratings": (1, 2, 3), "templates": (
        "the shower in room {room} drained very slowly and flooded the bathroom floor every morning",
        "no hot water in room {room} on the {floor} floor for about {hours} hours in the morning",
        "the toilet in room {room} kept running and the {fixture} was broken",
    )},
    {"key": "broken_fixture", "weight": 5, "ratings": (2, 3), "templates": (
        "the {fixture} in room {room} did not work and was not fixed during our {nights}-night stay",
        "the {fixture} in room {room} was broken, we reported it but nobody came",
    )},
    {"key": "wifi", "weight": 5, "ratings": (2, 3), "templates": (
        "the wifi kept dropping in room {room} on the {floor} floor, I could not join a work call",
        "internet was unusably slow in room {room}, it disconnected every few minutes",
    )},
    {"key": "billing_dispute", "weight": 5, "ratings": (1, 2), "templates": (
        "we were charged ${amount} for minibar items we never used and it took {minutes} minutes to sort out at {time}",
        "an extra ${amount} appeared on the bill at check-out and the {staff} could not explain it",
    )},
    {"key": "rude_staff", "weight": 5, "ratings": (1, 2), "templates": (
        "the {staff} was dismissive when we reported the problem in room {room} and walked away",
        "the {staff} was rude at {time} when we asked for help, no apology at all",
    )},
    {"key": "ac_smell", "weight": 4, "ratings": (2, 3), "templates": (
        "room {room} had a damp musty smell from the air conditioning that never went away",
    )},
    # --- Sporadic, severe, materially distinct incidents (stay as their own pinpointed issue) ---
    {"key": "pest_in_food", "weight": 2, "ratings": (1,), "templates": (
        "there was a cockroach in {item} at breakfast, I lost my appetite completely",
        "I found an insect crawling in {item} at the buffet, absolutely unacceptable for the price",
    )},
    {"key": "bedbugs", "weight": 1, "ratings": (1,), "templates": (
        "we woke up with bites all over and found bed bugs in the mattress of room {room}",
    )},
    {"key": "theft", "weight": 1, "ratings": (1,), "templates": (
        "${amount} went missing from room {room} after housekeeping visited and the {staff} was no help",
    )},
    {"key": "safety_alarm", "weight": 1, "ratings": (1, 2), "templates": (
        "the fire alarm in room {room} went off three times after {time} with no explanation from staff",
    )},
    {"key": "dirty_pool", "weight": 2, "ratings": (2, 3), "templates": (
        "the swimming pool was cloudy and full of leaves and was closed without notice on day {hours}",
    )},
)

_SCENARIO_BAG: tuple[dict[str, Any], ...] = tuple(
    scenario for scenario in SCENARIOS for _ in range(int(scenario["weight"]))
)

POSITIVE_TEMPLATES = (
    "the {staff} made check-in at {time} smooth and friendly, room {room} was spotless and comfortable",
    "breakfast was excellent, {item} was fresh and the {staff} was attentive",
    "room {room} on the {floor} floor was quiet and clean with a great view, housekeeping was thorough",
    "the {staff} went out of their way to help us, and the {room_type} room was very comfortable",
    "great location and a lovely calm stay, the {fixture} and everything in room {room} worked perfectly",
)

COUNTRIES = ("LK", "IN", "GB", "AU", "AE", "SG", "FR", "DE", "PK", "MV")
ROOM_NAMES = (
    "Deluxe Room",
    "Premium Ocean View Room",
    "Executive Room",
    "Harbour Suite",
    "Family Room",
)
TRIPADVISOR_LOCATIONS = (
    "Colombo, Sri Lanka",
    "Kandy, Sri Lanka",
    "Dubai, United Arab Emirates",
    "London, United Kingdom",
    "Singapore",
    "Mumbai, India",
)


@dataclass(frozen=True)
class ReviewDraft:
    text: str
    rating: int
    title: str | None = None


@dataclass(frozen=True)
class FixtureGenerationResult:
    output_dir: Path
    files: dict[str, Path]
    counts: dict[str, int]
    model: str
    generated_at: str


def platform_counts(total_reviews: int) -> dict[str, int]:
    if total_reviews < 0:
        raise ValueError("total_reviews must be non-negative")
    base = total_reviews // len(PLATFORMS)
    remainder = total_reviews % len(PLATFORMS)
    return {platform: base + (1 if index < remainder else 0) for index, platform in enumerate(PLATFORMS)}


def ollama_request(prompt: str, *, model: str = DEFAULT_MODEL, ollama_url: str = DEFAULT_OLLAMA_URL) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.9},
        }
    ).encode("utf-8")
    http_request = request.Request(
        ollama_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=120) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return str(response_payload.get("response", ""))


def extract_json_payload(raw_response: str) -> object:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [index for index in [cleaned.find("{"), cleaned.find("[")] if index >= 0]
        end_candidates = [index for index in [cleaned.rfind("}"), cleaned.rfind("]")] if index >= 0]
        if not start_candidates or not end_candidates:
            raise
        return json.loads(cleaned[min(start_candidates) : max(end_candidates) + 1])


def parse_review_draft(raw_response: str, *, fallback_rating: int) -> ReviewDraft:
    payload = extract_json_payload(raw_response)
    if isinstance(payload, dict) and isinstance(payload.get("review"), dict):
        payload = payload["review"]
    if not isinstance(payload, dict):
        raise ValueError("Ollama response must contain a JSON object.")
    text = str(payload.get("text") or payload.get("body") or payload.get("review_text") or "").strip()
    if not text:
        raise ValueError("Generated review text is empty.")
    title = str(payload.get("title") or "").strip() or None
    try:
        rating = int(float(payload.get("rating", fallback_rating)))
    except (TypeError, ValueError):
        rating = fallback_rating
    rating = min(5, max(1, rating))
    return ReviewDraft(text=text, title=title, rating=rating)


def build_prompt(*, platform: str, directive: str, rating: int, positive: bool, index: int) -> str:
    intent = (
        "Write a POSITIVE guest review about this good experience"
        if positive
        else "Write a guest review that complains about this specific problem"
    )
    return (
        "Generate one realistic hotel guest review for a connector fixture file.\n"
        "Return JSON only with exactly these keys: "
        '{"title":"optional short title", "text":"review body", "rating": 1}\n'
        f"Platform: {platform}\n"
        f"What happened (write the review about THIS exact incident): {directive}\n"
        f"Target rating: {rating}\n"
        f"Fixture row: {index}\n"
        "Rules:\n"
        f"- {intent}.\n"
        "- KEEP every concrete detail from the incident (room number, floor, item, amount, time, "
        "duration) in your review - these specifics are the whole point. Do not generalise them away.\n"
        "- You may add natural surrounding context, but do not invent a DIFFERENT problem.\n"
        "- Keep text between 25 and 130 words. Write in first person like a real guest.\n"
        "- Vary traveller type, wording, and tone.\n"
        "- Do not mention any hotel name, brand, property name, or city.\n"
        "- Do not include private identifiers, emails, phone numbers, reservation IDs, labels, or analysis.\n"
        "- Do not include sentiment labels, issue categories, department labels, reputation risk, or risk scores.\n"
        "- Do not include markdown, comments, or extra keys."
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def fallback_draft(*, directive: str, rating: int, positive: bool, index: int) -> ReviewDraft:
    # Deterministic fallback when the local model is unavailable or returns bad JSON. It still
    # carries the scenario specifics so the fixture is never generic.
    if positive:
        title = "Memorable stay"
        text = (
            f"Really enjoyed this stay. {directive[0].upper() + directive[1:]}. "
            "The team was attentive without being intrusive and everything felt well looked after."
        )
    else:
        title = "Stay needs attention"
        text = (
            f"Our stay was let down by one thing: {directive}. "
            "We raised it during the stay, and while staff were polite it affected how the visit went."
        )
    return ReviewDraft(text=text, title=title, rating=rating)


def build_review_draft(
    *,
    platform: str,
    directive: str,
    rating: int,
    positive: bool,
    index: int,
    request_text: Callable[[str], str] | None,
    model: str,
    ollama_url: str,
) -> ReviewDraft:
    prompt = build_prompt(platform=platform, directive=directive, rating=rating, positive=positive, index=index)
    if request_text is None:
        raw_response = ollama_request(prompt, model=model, ollama_url=ollama_url)
    else:
        raw_response = request_text(prompt)
    try:
        draft = parse_review_draft(raw_response, fallback_rating=rating)
    except (json.JSONDecodeError, ValueError):
        draft = fallback_draft(directive=directive, rating=rating, positive=positive, index=index)
    return ReviewDraft(text=normalize_text(draft.text), title=draft.title, rating=draft.rating)


def review_datetime(
    index: int,
    *,
    total_reviews: int = DEFAULT_TOTAL_REVIEWS,
    date_window_start: datetime = DEFAULT_DATE_WINDOW_START,
    date_window_end: datetime = DEFAULT_DATE_WINDOW_END,
) -> datetime:
    if total_reviews <= 1:
        return date_window_start
    offset = (date_window_end - date_window_start) * ((index - 1) / (total_reviews - 1))
    return date_window_start + offset


def reviewer_alias(index: int) -> str:
    names = (
        "Ayesha F",
        "Nuwan P",
        "Maya K",
        "HariniW",
        "TravelWithRavi",
        "Sophie M",
        "BusinessGuest42",
        "ColomboVisitor",
        "Samir A",
        "WeekendTraveller",
    )
    return f"{names[index % len(names)]}{index:04d}"


def maybe_reply(
    index: int,
    rating: int,
    *,
    total_reviews: int,
    date_window_start: datetime,
    date_window_end: datetime,
) -> dict[str, str] | None:
    if rating >= 4 or index % 3:
        return None
    created = review_datetime(
        index,
        total_reviews=total_reviews,
        date_window_start=date_window_start,
        date_window_end=date_window_end,
    )
    return {
        "comment": "Thank you for the detailed feedback. Our team is reviewing this with the relevant manager.",
        "updateTime": min(created + timedelta(days=1), date_window_end).isoformat().replace("+00:00", "Z"),
    }


def google_payload(
    index: int,
    draft: ReviewDraft,
    rng: random.Random,
    *,
    total_reviews: int,
    date_window_start: datetime,
    date_window_end: datetime,
) -> dict[str, Any]:
    review_id = f"gbp-review-{index:06d}"
    created = review_datetime(
        index,
        total_reviews=total_reviews,
        date_window_start=date_window_start,
        date_window_end=date_window_end,
    )
    updated = min(created + timedelta(hours=rng.randint(0, 72)), date_window_end)
    payload: dict[str, Any] = {
        "name": f"accounts/1029384756/locations/8945123001/reviews/{review_id}",
        "reviewId": review_id,
        "reviewer": {
            "displayName": reviewer_alias(index),
            "profilePhotoUrl": f"https://lh3.googleusercontent.com/a/fixture-{index:06d}",
            "isAnonymous": index % 11 == 0,
        },
        "starRating": STAR_RATING_NAMES[draft.rating],
        "comment": draft.text,
        "createTime": created.isoformat().replace("+00:00", "Z"),
        "updateTime": updated.isoformat().replace("+00:00", "Z"),
        "likeCount": rng.randint(0, 18),
    }
    reply = maybe_reply(
        index,
        draft.rating,
        total_reviews=total_reviews,
        date_window_start=date_window_start,
        date_window_end=date_window_end,
    )
    if reply is not None:
        payload["reviewReply"] = reply
    return payload


def booking_payload(
    index: int,
    draft: ReviewDraft,
    rng: random.Random,
    *,
    total_reviews: int,
    date_window_start: datetime,
    date_window_end: datetime,
) -> dict[str, Any]:
    created = review_datetime(
        index,
        total_reviews=total_reviews,
        date_window_start=date_window_start,
        date_window_end=date_window_end,
    )
    updated = min(created + timedelta(hours=rng.randint(1, 48)), date_window_end)
    overall = round(draft.rating * 2.0, 1)
    variance = lambda: max(1.0, min(10.0, round(overall + rng.choice((-1.0, -0.5, 0.0, 0.5, 1.0)), 1)))
    negative = "" if draft.rating >= 4 else draft.text
    positive = draft.text if draft.rating >= 4 else "The location was convenient and several staff members tried to help."
    return {
        "guest_review_id": f"booking-review-{index:06d}",
        "hotel_id": "kingsbury-colombo-demo",
        "reservation_id": f"booking-res-{700000 + index}",
        "reviewer": {
            "name": reviewer_alias(index),
            "country_code": COUNTRIES[index % len(COUNTRIES)],
            "stayed_room_name": ROOM_NAMES[index % len(ROOM_NAMES)],
        },
        "scores": {
            "overall": overall,
            "cleanliness": variance(),
            "comfort": variance(),
            "facilities": variance(),
            "staff": variance(),
            "value_for_money": variance(),
        },
        "content": {
            "headline": draft.title or ("Excellent hotel team" if draft.rating >= 4 else "Mixed stay"),
            "positive": positive,
            "negative": negative,
            "language_code": "en",
        },
        "created_at": created.isoformat(),
        "updated_at": updated.isoformat(),
        "review_status": "published",
        "helpful_votes": rng.randint(0, 24),
        "partner_response_status": "responded" if draft.rating <= 2 and index % 2 == 0 else "not_responded",
    }


def tripadvisor_payload(
    index: int,
    draft: ReviewDraft,
    rng: random.Random,
    *,
    total_reviews: int,
    date_window_start: datetime,
    date_window_end: datetime,
) -> dict[str, Any]:
    created = review_datetime(
        index,
        total_reviews=total_reviews,
        date_window_start=date_window_start,
        date_window_end=date_window_end,
    )
    payload: dict[str, Any] = {
        "id": f"tripadvisor-review-{index:06d}",
        "location_id": "the-kingsbury-colombo-demo",
        "url": f"https://www.tripadvisor.com/ShowUserReviews-g293962-d301921-r{index:06d}-The_Kingsbury_Colombo.html",
        "rating": draft.rating,
        "published_date": created.isoformat(),
        "travel_date": created.strftime("%Y-%m"),
        "title": draft.title or ("Good Colombo base" if draft.rating >= 4 else "Could be better"),
        "text": draft.text,
        "user": {
            "username": reviewer_alias(index).replace(" ", ""),
            "user_location": {"name": TRIPADVISOR_LOCATIONS[index % len(TRIPADVISOR_LOCATIONS)]},
            "contributions": rng.randint(1, 280),
            "helpful_votes": rng.randint(0, 90),
        },
        "subratings": {
            "service": max(1, min(5, draft.rating + rng.choice((-1, 0, 1)))),
            "value": max(1, min(5, draft.rating + rng.choice((-1, 0, 1)))),
            "sleep_quality": max(1, min(5, draft.rating + rng.choice((-1, 0, 1)))),
            "cleanliness": max(1, min(5, draft.rating + rng.choice((-1, 0, 1)))),
        },
        "photos": [{"id": f"photo-{index:06d}", "caption": "Guest uploaded hotel photo"}] if index % 17 == 0 else [],
    }
    if draft.rating <= 3 and index % 3 == 0:
        payload["management_response"] = {
            "text": "We appreciate the feedback and are reviewing the concern with our operations team.",
            "published_date": min(created + timedelta(days=1), date_window_end).isoformat(),
        }
    return payload


def platform_payload(
    platform: str,
    index: int,
    draft: ReviewDraft,
    rng: random.Random,
    *,
    total_reviews: int,
    date_window_start: datetime,
    date_window_end: datetime,
) -> dict[str, Any]:
    if platform == "google_business_profile":
        return google_payload(
            index,
            draft,
            rng,
            total_reviews=total_reviews,
            date_window_start=date_window_start,
            date_window_end=date_window_end,
        )
    if platform == "booking_com":
        return booking_payload(
            index,
            draft,
            rng,
            total_reviews=total_reviews,
            date_window_start=date_window_start,
            date_window_end=date_window_end,
        )
    if platform == "tripadvisor":
        return tripadvisor_payload(
            index,
            draft,
            rng,
            total_reviews=total_reviews,
            date_window_start=date_window_start,
            date_window_end=date_window_end,
        )
    raise ValueError(f"Unsupported platform {platform!r}")


def prefixed_identifier(value: str, namespace: str) -> str:
    if not namespace:
        return value
    prefix = f"{namespace}-"
    return value if value.startswith(prefix) else f"{prefix}{value}"


def namespace_payload_ids(platform: str, payload: dict[str, Any], namespace: str) -> None:
    if not namespace:
        return
    if platform == "google_business_profile":
        old_id = payload["reviewId"]
        new_id = prefixed_identifier(old_id, namespace)
        payload["reviewId"] = new_id
        payload["name"] = str(payload["name"]).removesuffix(old_id) + new_id
        return
    if platform == "booking_com":
        payload["guest_review_id"] = prefixed_identifier(payload["guest_review_id"], namespace)
        payload["reservation_id"] = prefixed_identifier(payload["reservation_id"], namespace)
        return
    if platform == "tripadvisor":
        old_id = payload["id"]
        new_id = prefixed_identifier(old_id, namespace)
        payload["id"] = new_id
        match = re.search(r"tripadvisor-review-(\d+)$", old_id)
        if match:
            payload["url"] = str(payload["url"]).replace(f"-r{match.group(1)}-", f"-r{namespace}-{match.group(1)}-")
        return
    raise ValueError(f"Unsupported platform {platform!r}")


def scenario_for_index(index: int, rng: random.Random) -> tuple[str, int, bool]:
    """Return (directive, rating, positive). Roughly 1 in 4 reviews is positive; the rest draw a
    weighted negative scenario and fill it with concrete specifics."""
    if index % 4 == 0:
        directive = _fill(rng.choice(POSITIVE_TEMPLATES), rng)
        return directive, rng.choice((4, 5)), True
    scenario = rng.choice(_SCENARIO_BAG)
    directive = _fill(rng.choice(scenario["templates"]), rng)
    rating = rng.choice(scenario["ratings"])
    return directive, rating, False


def contains_analysis_fields(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).lower()
            if normalized_key in ANALYSIS_FIELD_NAMES:
                return True
            if contains_analysis_fields(nested_value):
                return True
    elif isinstance(value, list):
        return any(contains_analysis_fields(item) for item in value)
    return False


def write_platform_file(output_dir: Path, platform: str, payloads: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{platform}.json"
    output_path.write_text(json.dumps(payloads, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def generate_connector_fixtures(
    *,
    output_dir: Path | None = None,
    total_reviews: int = DEFAULT_TOTAL_REVIEWS,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    request_text: Callable[[str], str] | None = None,
    seed: int = 202607,
    date_window_start: datetime = DEFAULT_DATE_WINDOW_START,
    date_window_end: datetime = DEFAULT_DATE_WINDOW_END,
    id_namespace: str = "",
    log: Callable[[str], None] | None = None,
) -> FixtureGenerationResult:
    if date_window_end < date_window_start:
        raise ValueError("date_window_end must be on or after date_window_start")
    rng = random.Random(seed)
    counts = platform_counts(total_reviews)
    files: dict[str, Path] = {}
    generated_at = datetime.now(UTC).isoformat()

    for platform in PLATFORMS:
        payloads: list[dict[str, Any]] = []
        for local_index in range(1, counts[platform] + 1):
            global_index = sum(counts[prior] for prior in PLATFORMS[: PLATFORMS.index(platform)]) + local_index
            directive, rating, positive = scenario_for_index(global_index, rng)
            draft = build_review_draft(
                platform=platform,
                directive=directive,
                rating=rating,
                positive=positive,
                index=global_index,
                request_text=request_text,
                model=model,
                ollama_url=ollama_url,
            )
            payload = platform_payload(
                platform,
                global_index,
                draft,
                rng,
                total_reviews=total_reviews,
                date_window_start=date_window_start,
                date_window_end=date_window_end,
            )
            namespace_payload_ids(platform, payload, id_namespace)
            if contains_analysis_fields(payload):
                raise ValueError(f"Generated {platform} payload contains precomputed analysis fields.")
            payloads.append(payload)
            if log is not None:
                log(f"{platform}: generated {local_index}/{counts[platform]}")
        files[platform] = write_platform_file(output_dir, platform, payloads)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "model": model,
                "ollama_url": ollama_url,
                "total_reviews": total_reviews,
                "date_window_start": date_window_start.isoformat(),
                "date_window_end": date_window_end.isoformat(),
                "id_namespace": id_namespace or None,
                "counts": counts,
                "files": {platform: str(path) for platform, path in files.items()},
                "product_runtime": "not used; generation is a local data-preparation step",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["manifest"] = manifest_path
    return FixtureGenerationResult(
        output_dir=output_dir,
        files=files,
        counts=counts,
        model=model,
        generated_at=generated_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate connector-shaped review fixture JSON files with local Ollama outside product runtime."
    )
    parser.add_argument("--total-reviews", type=int, default=DEFAULT_TOTAL_REVIEWS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--seed", type=int, default=202607)
    parser.add_argument("--date-window-start", default=DEFAULT_DATE_WINDOW_START.isoformat())
    parser.add_argument("--date-window-end", default=DEFAULT_DATE_WINDOW_END.isoformat())
    parser.add_argument("--id-namespace", default="")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs.")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _default_output_dir(model: str) -> Path:
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", model).strip("-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_BASE / f"connectors-{sanitized}-{timestamp}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    output_dir = args.output_dir or _default_output_dir(args.model)
    result = generate_connector_fixtures(
        output_dir=output_dir,
        total_reviews=args.total_reviews,
        model=args.model,
        ollama_url=args.ollama_url,
        seed=args.seed,
        date_window_start=datetime.fromisoformat(args.date_window_start),
        date_window_end=datetime.fromisoformat(args.date_window_end),
        id_namespace=args.id_namespace,
        log=None if args.quiet else lambda message: print(message, flush=True),
    )
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "counts": result.counts,
                "files": {platform: str(path) for platform, path in result.files.items()},
                "model": result.model,
                "generated_at": result.generated_at,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
