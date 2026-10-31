import pytest
from pydantic import ValidationError
from app.customer_api import AddressRequest


def test_address_coordinates_are_optional_and_validated_as_pair():
    values = dict(label="Home", address="Flat 1, Main Road", city="Maval", pincode="410507")
    assert AddressRequest(**values).latitude is None
    address = AddressRequest(**values, latitude=18.75, longitude=73.67)
    assert (address.latitude, address.longitude) == (18.75, 73.67)
    with pytest.raises(ValidationError):
        AddressRequest(**values, latitude=18.75)
    with pytest.raises(ValidationError):
        AddressRequest(**values, latitude=91, longitude=73)
