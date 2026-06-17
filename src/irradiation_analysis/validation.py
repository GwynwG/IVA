import math
import re
from numbers import Real


ROOM_RE = re.compile(r"^R(?:0[1-9]|1[0-9]|20)$")
DEVICE_RE = re.compile(r"^(R(?:0[1-9]|1[0-9]|20))-D(?:0[1-9]|10)$")


def validate_room_device_ids(room_id: str, device_id: str) -> list[str]:
    issues: list[str] = []

    if ROOM_RE.fullmatch(room_id) is None:
        issues.append("room_id must be between R01 and R20")

    device_match = DEVICE_RE.fullmatch(device_id)
    if device_match is None:
        issues.append("device_id must use Rxx-D01 through Rxx-D10")
    elif device_match.group(1) != room_id:
        issues.append("device_id room prefix must match room_id")

    return issues


def is_finite_number(value: object) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
