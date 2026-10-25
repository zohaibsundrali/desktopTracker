import unittest

from app_monitor import AppSession, sanitize_title


class WindowTitleSanitizationTests(unittest.TestCase):
    def assert_redacted(self, raw, *secrets):
        cleaned = sanitize_title(raw)
        for secret in secrets:
            self.assertNotIn(secret, cleaned)
        return cleaned

    def test_query_fragment_and_named_secret_variants_are_removed(self):
        cleaned = self.assert_redacted(
            "Login https://app.test/callback?code=oauth-code&state=private "
            "access token: token-value API key=key-value user@example.test",
            "oauth-code", "private", "token-value", "key-value", "user@example.test",
        )
        self.assertIn("?[redacted]", cleaned)
        self.assertIn("[email]", cleaned)

    def test_bearer_jwt_provider_keys_and_url_passwords_are_removed(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
        raw = (
            f"Authorization: Bearer {jwt} · standalone {jwt} · "
            "sk_live_1234567890 · sb_secret_abcdefghijkl · "
            "https://alice:private-password@example.test/report"
        )
        cleaned = self.assert_redacted(
            raw, jwt, "sk_live_1234567890", "sb_secret_abcdefghijkl",
            "alice", "private-password",
        )
        self.assertIn("https://[redacted]@example.test/report", cleaned)

    def test_model_sanitizes_again_and_caps_untrusted_title(self):
        raw = "Report token=private-value " + ("x" * 300)
        session = AppSession("editor.exe", raw, __import__("datetime").datetime.now())
        self.assertNotIn("private-value", session.window_title)
        self.assertLessEqual(len(session.window_title), 151)
        self.assertTrue(session.window_title.endswith("…"))


if __name__ == "__main__":
    unittest.main()
