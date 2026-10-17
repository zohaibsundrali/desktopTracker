import unittest
from datetime import datetime

import site_detector
from app_monitor import AppMonitor


class SiteDetectorTests(unittest.TestCase):
    def test_known_ai_sites_are_named_from_title(self):
        self.assertEqual(site_detector.site_from_title("New chat - ChatGPT"), "ChatGPT")
        self.assertEqual(site_detector.site_from_title("DeepThink - DeepSeek"), "DeepSeek")

    def test_known_ai_sites_are_named_from_domain(self):
        self.assertEqual(site_detector.label_from_domain(site_detector._domain("https://chatgpt.com/c/123")), "ChatGPT")
        self.assertEqual(site_detector.label_from_domain(site_detector._domain("https://api.deepseek.com/chat")), "DeepSeek")

    def test_address_bar_fallback_rejects_arbitrary_page_text(self):
        self.assertEqual(site_detector._domain("write me a secret plan"), "")
        self.assertEqual(site_detector._domain("token=private"), "")


class LiveSiteTests(unittest.TestCase):
    def test_live_sites_are_ranked_and_mark_current(self):
        monitor = AppMonitor.__new__(AppMonitor)
        import threading
        monitor._lock = threading.Lock()
        now = datetime.now()
        monitor._current_site = "DeepSeek"
        monitor._site_seconds = {
            "ChatGPT": {"seconds": 90, "first": now, "last": now},
            "DeepSeek": {"seconds": 120, "first": now, "last": now},
        }

        sites = monitor.live_sites()

        self.assertEqual([row["site_name"] for row in sites], ["DeepSeek", "ChatGPT"])
        self.assertTrue(sites[0]["is_foreground"])
        self.assertEqual(sites[0]["duration_seconds"], 120)


if __name__ == "__main__":
    unittest.main()
