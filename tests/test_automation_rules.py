import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def make_task(**overrides):
    now = datetime(2026, 4, 16, 12, 0, 0)
    task = {
        "id": 1,
        "title": "Test task",
        "description": "",
        "status": "pending",
        "priority": "medium",
        "due_date": None,
        "source": "",
        "sender": "",
        "raw_text": "",
        "created_at": (now - timedelta(days=2)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
    }
    task.update(overrides)
    return task


class AutomationRulesTest(unittest.TestCase):
    def test_pending_task_becomes_silent_after_48_hours(self):
        now = datetime(2026, 4, 16, 12, 0, 0)
        task = make_task(status="pending", updated_at=(now - timedelta(hours=49)).isoformat())

        result = app.evaluate_task_automation(task, now)

        self.assertIn("silent", result["states"])
        self.assertIn("silent", result["reasons"])

    def test_done_task_becomes_auto_archived_after_3_days(self):
        now = datetime(2026, 4, 16, 12, 0, 0)
        task = make_task(status="done", updated_at=(now - timedelta(days=4)).isoformat())

        result = app.evaluate_task_automation(task, now)

        self.assertIn("auto_archived", result["states"])

    def test_due_today_is_not_overdue_for_date_only_field(self):
        now = datetime(2026, 4, 17, 14, 30, 0)
        task = make_task(
            status="in_progress",
            due_date="2026-04-17",
            updated_at=(now - timedelta(hours=1)).isoformat(),
        )

        result = app.evaluate_task_automation(task, now)

        self.assertNotIn("overdue", result["states"])

    def test_archived_done_task_reactivates_when_new_activity_appears(self):
        now = datetime(2026, 4, 16, 12, 0, 0)
        task = make_task(
            status="done",
            updated_at=(now - timedelta(hours=1)).isoformat(),
            automation={
                "state": ["auto_archived"],
                "reason": {"auto_archived": "done_for_3_days"},
                "updated_at": (now - timedelta(days=4)).isoformat(),
                "archived_at": (now - timedelta(days=4)).isoformat(),
                "reactivated_at": None,
                "last_notified_at": None,
                "notification_keys": [],
            },
        )

        result = app.evaluate_task_automation(task, now)

        self.assertIn("reactivated", result["states"])
        self.assertNotIn("auto_archived", result["states"])


if __name__ == "__main__":
    unittest.main()
