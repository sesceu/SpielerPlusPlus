"""
iCalendar (.ics) Augmenter and Merger.
Parses official SpielerPlus .ics feeds, augments them with team shortcodes
and personal attendance status emojis, and merges multiple team feeds.
"""

from __future__ import annotations

import datetime
import re
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

STATUS_EMOJI_MAP: Dict[str, str] = {
    "zugesagt": "👍",
    "abgesagt": "👎",
    "unsicher": "❓",
    "offen": "⏳",
    "nicht_nominiert": "🚫",
}

STATUS_LABEL_MAP: Dict[str, str] = {
    "zugesagt": "Zugesagt",
    "abgesagt": "Abgesagt",
    "unsicher": "Unsicher",
    "offen": "Noch offen",
    "nicht_nominiert": "Nicht nominiert",
}


def build_event_summary(
    title: str,
    shortcode: Optional[str] = None,
    status: Optional[str] = None,
    include_emoji: bool = True,
) -> str:
    """Format event title with optional team shortcode and attendance status emoji."""
    prefix_parts = []
    if shortcode and shortcode.strip():
        prefix_parts.append(shortcode.strip())

    if include_emoji and status:
        emoji = STATUS_EMOJI_MAP.get(status.lower(), "⏳")
        prefix_parts.append(emoji)

    if prefix_parts:
        prefix = f"[{', '.join(prefix_parts)}]"
        return f"{prefix} {title}".strip()
    return title.strip()


def extract_event_info(vevent: Event) -> Optional[Tuple[str, int]]:
    """
    Extract (event_type, event_id) from an iCalendar VEVENT.
    Checks UID (e.g. 'training.74856637') and URL (e.g. '.../training/view?id=74856637').
    """
    # 1. Try UID: e.g. "training.74856637" or "game-14557386"
    uid = str(vevent.get("uid", "")).strip()
    m_uid = re.match(r"(training|game|event|tournament)[.-](\d+)", uid, re.IGNORECASE)
    if m_uid:
        return m_uid.group(1).lower(), int(m_uid.group(2))

    # 2. Try URL
    url = str(vevent.get("url", "")).strip()
    m_url = re.search(r"/(training|game|event|tournament)/view\?id=(\d+)", url, re.IGNORECASE)
    if m_url:
        return m_url.group(1).lower(), int(m_url.group(2))

    return None


def is_absence_event(vevent: Event) -> bool:
    """Check if event is a user-declared personal absence placeholder."""
    uid = str(vevent.get("uid", "")).strip().lower()
    if uid.startswith("absence.") or uid.startswith("absence-"):
        return True
    summary = str(vevent.get("summary", "")).strip().lower()
    summary_clean = re.sub(r"^\[.*?\]\s*", "", summary)
    return summary_clean.startswith("abwesend") or summary_clean.startswith("abwesenheit")


def is_event_upcoming(
    vevent: Event,
    days_ahead: int = 90,
    reference_time: Optional[datetime.datetime] = None,
) -> bool:
    """Check if event is upcoming and within query window (ref - 1 day to ref + days_ahead)."""
    dtstart = vevent.get("dtstart")
    if not dtstart or not hasattr(dtstart, "dt"):
        return True

    event_dt = dtstart.dt
    ref = reference_time or datetime.datetime.now(datetime.timezone.utc)

    # Convert date to datetime if necessary
    if isinstance(event_dt, datetime.date) and not isinstance(event_dt, datetime.datetime):
        event_dt = datetime.datetime(event_dt.year, event_dt.month, event_dt.day, tzinfo=ref.tzinfo)

    # Make comparison timezone-aware or naive
    if event_dt.tzinfo is None and ref.tzinfo is not None:
        event_dt = event_dt.replace(tzinfo=ref.tzinfo)
    elif event_dt.tzinfo is not None and ref.tzinfo is None:
        ref = ref.replace(tzinfo=event_dt.tzinfo)

    start_threshold = ref - datetime.timedelta(days=1)
    end_threshold = ref + datetime.timedelta(days=days_ahead)
    return start_threshold <= event_dt <= end_threshold


def augment_event(
    vevent: Event,
    shortcode: Optional[str] = None,
    user_status: Optional[str] = None,
    include_emoji: bool = True,
) -> None:
    """Augment VEVENT summary and description with shortcode and attendance status."""
    orig_summary = str(vevent.get("summary", "")).strip()
    new_summary = build_event_summary(
        title=orig_summary,
        shortcode=shortcode,
        status=user_status,
        include_emoji=include_emoji,
    )
    vevent["summary"] = new_summary

    if user_status:
        label = STATUS_LABEL_MAP.get(user_status.lower(), user_status)
        emoji = STATUS_EMOJI_MAP.get(user_status.lower(), "")
        status_line = f"👤 Eigener Status: {label} {emoji}".strip()

        desc = str(vevent.get("description", "")).strip()
        if desc:
            vevent["description"] = f"{status_line}\n\n{desc}"
        else:
            vevent["description"] = status_line
