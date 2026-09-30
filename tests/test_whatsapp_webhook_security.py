import hashlib
import hmac
import unittest

from app.whatsapp_webhook_security import verify_meta_signature


class WhatsAppWebhookSecurityTests(unittest.TestCase):
    def test_valid_meta_signature(self):
        body = b'{"entry":[]}'
        secret = "test-app-secret"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_meta_signature(body, "sha256=" + digest, secret))

    def test_tampered_body_is_rejected(self):
        body = b'{"entry":[]}'
        secret = "test-app-secret"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertFalse(verify_meta_signature(body + b"x", "sha256=" + digest, secret))

    def test_missing_or_malformed_signature_is_rejected(self):
        body = b'{"entry":[]}'
        secret = "test-app-secret"
        self.assertFalse(verify_meta_signature(body, None, secret))
        self.assertFalse(verify_meta_signature(body, "", secret))
        self.assertFalse(verify_meta_signature(body, "bad=" + "0" * 64, secret))
        self.assertFalse(verify_meta_signature(body, "sha256=" + "0" * 63, secret))
        self.assertFalse(verify_meta_signature(body, "sha256=" + "0" * 64, None))


if __name__ == "__main__":
    unittest.main()
