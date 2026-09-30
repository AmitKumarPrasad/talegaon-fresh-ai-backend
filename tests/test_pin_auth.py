from app.pin_auth import _pin_hash, _pin_matches

def test_pin_hash_is_not_plaintext_and_verifies():
    encoded = _pin_hash("123456")
    assert encoded.startswith("scrypt$")
    assert encoded != "123456"
    assert _pin_matches("123456", encoded)
    assert not _pin_matches("123457", encoded)

def test_pin_hash_uses_unique_salt():
    first = _pin_hash("123456")
    second = _pin_hash("123456")
    assert first != second
    assert _pin_matches("123456", first)
    assert _pin_matches("123456", second)
