from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import selector
from homeassistant.util.yaml import load_yaml

from custom_components.car_share_assistant.services import interval


def test_all_action_selectors_are_valid():
    from pathlib import Path

    services = load_yaml(str(Path(__file__).parent.parent / "custom_components/car_share_assistant/services.yaml"))
    for service in services.values():
        for field in service["fields"].values():
            selector.validate_selector(field["selector"])


@pytest.mark.parametrize(
    ("start", "end"), [("2026-03-29T02:15:00", "2026-03-29T03:30:00"), ("2026-10-25T02:15:00", "2026-10-25T03:30:00")]
)
def test_local_dst_ambiguity_and_missing_hour_are_rejected(start, end):
    with pytest.raises(ServiceValidationError):
        interval({"start_time": start, "end_time": end}, ZoneInfo("Europe/Amsterdam"))


def test_local_times_receive_correct_summer_and_winter_offsets():
    for month, offset in [("06", "+02:00"), ("12", "+01:00")]:
        start, end = interval(
            {"start_time": f"2026-{month}-12T09:00:00", "end_time": f"2026-{month}-12T17:00:00"},
            ZoneInfo("Europe/Amsterdam"),
        )
        assert start.isoformat().endswith(offset)
        assert end.isoformat().endswith(offset)
