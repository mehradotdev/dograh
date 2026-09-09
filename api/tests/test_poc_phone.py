import pytest

from api.services.poc.phone import (
    InvalidCallerNumber,
    masked_mobile,
    normalize_indian_mobile,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("98765-43210", "9876543210"),
    ],
)
def test_normalize_indian_mobile(raw, expected):
    assert normalize_indian_mobile(raw) == expected


def test_rejects_invalid_or_landline_number():
    with pytest.raises(InvalidCallerNumber):
        normalize_indian_mobile("1234")


def test_masks_caller():
    assert masked_mobile("+91 98765 43210") == "******3210"
    assert masked_mobile("hidden") == "unknown"
