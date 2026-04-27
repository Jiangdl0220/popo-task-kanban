import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def make_task(**overrides):
    now = datetime(2026, 4, 16, 12, 0, 0)
    task = {
        "id": 1,
        "title": "Notify task",
        "description": "",
        "status": "done",
        "priority": "medium",
        "due_date": None,
        "source": "",
        "sender": "",
        "raw_text": "",
        "created_at": (now - timedelta(days=5)).isoformat(),
        "updated_at": (now - timedelta(days=4)).isoformat(),
    }
    task.update(overrides)
    return task


class AutomationNotificationTest(unittest.TestCase):
    def test_openclaw_notification_is_sent_once_for_new_event(self):
        now = datetime(2026, 4, 16, 12, 0, 0)
        task = make_task()
        tasks = [task]
        original_webhook = getattr(app, "AUTOMATION_WEBHOOK_URL", "")
        app.AUTOMATION_WEBHOOK_URL = "http://openclaw.local/automation"

        response = MagicMock()
        response.read.return_value = b"{}"
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch("app.urllib.request.urlopen", return_value=response) as mocked:
            first = app.scan_all_tasks_for_automation(tasks, trigger_source="manual_scan", now=now)
            second = app.scan_all_tasks_for_automation(tasks, trigger_source="manual_scan", now=now)

        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(first["events"][0]["state"], "auto_archived")
        self.assertEqual(len(second["events"]), 0)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(tasks[0]["automation"]["notification_keys"][0], first["events"][0]["notification_key"])
        app.AUTOMATION_WEBHOOK_URL = original_webhook


if __name__ == "__main__":
    unittest.main()
