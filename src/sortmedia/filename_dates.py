"""Parse filename dates without guessing regional date order."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


DATE_ORDERS = ("ymd", "dmy", "mdy")
_YEAR_FIRST = (
    re.compile(r"(?<![\d.:])(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?!\d)"),
    re.compile(r"(?<![\d.:])(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?!\d)"),
)
_REGIONAL = {
    "dmy": re.compile(r"(?<![\d.:])(?P<day>\d{2})-(?P<month>\d{2})-(?P<year>\d{4})(?!\d)"),
    "mdy": re.compile(r"(?<![\d.:])(?P<month>\d{2})-(?P<day>\d{2})-(?P<year>\d{4})(?!\d)"),
}
_TIME_START = re.compile(r"^[ T_-]+(?=\d{1,2}[-:.]|\d{6})")
_TIMES = (
    re.compile(r"[ T_-]+(?P<hour>\d{1,2})(?P<sep>[-:.])(?P<minute>\d{2})(?P=sep)(?P<second>\d{2})(?:\.(?P<fraction>\d{1,6}))?(?![\d.:])"),
    re.compile(r"[ T_-]+(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})(?:\.(?P<fraction>\d{1,6}))?(?![\d.:])"),
)
_ZONE = re.compile(r"Z(?:$|[_ -])|[+-]\d{2}:?\d{2}")


def validate_date_order(value: object) -> str:
    if not isinstance(value, str) or value not in DATE_ORDERS:
        raise ValueError("filename_date_order must be ymd, dmy, or mdy")
    return value


@dataclass(frozen=True)
class FilenameDate:
    value: datetime
    start: int
    end: int
    has_time: bool


def parse_filename_date(stem: str, date_order: str = "ymd", *, anchored: bool = False) -> FilenameDate | None:
    """Prefer a complete timestamp to date-only matches; skip invalid tokens.

    Date-only values use midnight and retain their precision in has_time.
    Year-first formats remain available for every regional setting.
    Fractional digits are padded as text so leading zeros are preserved.
    """
    validate_date_order(date_order)
    patterns = _YEAR_FIRST + ((_REGIONAL[date_order],) if date_order != "ymd" else ())
    candidates: list[FilenameDate] = []
    for pattern in patterns:
        for match in pattern.finditer(stem):
            if anchored and match.start() != 0:
                continue
            fields = {key: int(value) for key, value in match.groupdict().items()}
            end = match.end()
            suffix = stem[end:]
            clock = None
            next_token = suffix.lstrip(" _-")
            next_is_date = False
            for regex in patterns:
                following = regex.match(next_token)
                if following is not None:
                    try:
                        datetime(**{key: int(value) for key, value in following.groupdict().items()})
                    except ValueError:
                        continue
                    next_is_date = True
                    break
            if _TIME_START.match(suffix) and not next_is_date:
                clock = next((found for regex in _TIMES if (found := regex.match(suffix))), None)
                if clock is None:
                    continue
                for key in ("hour", "minute", "second"):
                    fields[key] = int(clock[key])
                fraction = clock["fraction"]
                if fraction:
                    fields["microsecond"] = int(fraction.ljust(6, "0"))
                end += clock.end()
                # Filename timezone suffixes are outside the supported local-clock formats.
                if _ZONE.match(stem[end:]):
                    continue
            try:
                value = datetime(**fields)
            except ValueError:
                continue
            candidates.append(FilenameDate(value, match.start(), end, clock is not None))
    return min(candidates, key=lambda item: (not item.has_time, item.start)) if candidates else None
