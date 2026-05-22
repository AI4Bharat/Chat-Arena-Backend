"""
Tests for common.security_utils — sanitize_error_message().

Verifies that API keys, Bearer tokens, hex secrets, and long base64 tokens
are redacted from error messages before they reach the client.
"""
from django.test import TestCase
from common.security_utils import sanitize_error_message


class SanitizeErrorMessageTests(TestCase):
    """Test sanitize_error_message() redacts sensitive data."""

    # ── Bearer tokens ──────────────────────────────────────────────
    def test_redacts_bearer_token(self):
        exc = Exception("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123")
        result = sanitize_error_message(exc)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", result)
        self.assertIn("***REDACTED***", result)

    # ── OpenAI-style sk- keys ──────────────────────────────────────
    def test_redacts_openai_key(self):
        exc = Exception("OpenAI error with key sk-abc123DEF456ghi789jkl012mno345pqr678stu901vwx")
        result = sanitize_error_message(exc)
        self.assertNotIn("sk-abc123DEF456", result)
        self.assertIn("sk-***REDACTED***", result)

    # ── Hex strings (Azure-style keys) ─────────────────────────────
    def test_redacts_hex_key(self):
        hex_key = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        exc = Exception(f"Azure error: key={hex_key}")
        result = sanitize_error_message(exc)
        self.assertNotIn(hex_key, result)
        self.assertIn("***REDACTED", result)

    # ── API key in URL query params ────────────────────────────────
    def test_redacts_api_key_in_url(self):
        exc = Exception("Request to https://api.example.com/v1?key=MY_SUPER_SECRET_KEY_12345 failed")
        result = sanitize_error_message(exc)
        self.assertNotIn("MY_SUPER_SECRET_KEY_12345", result)
        self.assertIn("key=***REDACTED***", result)

    def test_redacts_token_in_url(self):
        exc = Exception("https://api.example.com?token=secretValue123&other=1")
        result = sanitize_error_message(exc)
        self.assertNotIn("secretValue123", result)
        self.assertIn("token=***REDACTED***", result)

    # ── Preserves normal messages ──────────────────────────────────
    def test_preserves_normal_message(self):
        msg = "Connection refused: host=localhost port=5432"
        exc = Exception(msg)
        result = sanitize_error_message(exc)
        self.assertIn("Connection refused", result)
        self.assertIn("localhost", result)

    def test_preserves_short_message(self):
        msg = "Not found"
        exc = Exception(msg)
        result = sanitize_error_message(exc)
        self.assertEqual(result, "Not found")

    # ── Accepts string input ───────────────────────────────────────
    def test_accepts_string_input(self):
        result = sanitize_error_message("raw string with sk-abcdefghijklmnopqrstuvwxyz1234567890")
        self.assertIn("sk-***REDACTED***", result)
