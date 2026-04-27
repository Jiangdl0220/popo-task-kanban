import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def make_task(**overrides):
    now = datetime(2026, 4, 16, 12, 0, 0)
    task = {
        "id": 1,
        "title": "API task",
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


class AutomationApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_file = Path(self.temp_dir.name) / "tasks.json"
        self.original_tasks_file = app.TASKS_FILE
        app.TASKS_FILE = str(self.tasks_file)
        self.client = app.app.test_client()

    def tearDown(self):
        app.TASKS_FILE = self.original_tasks_file
        self.temp_dir.cleanup()

    def write_tasks(self, tasks):
        self.tasks_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_tasks(self):
        return json.loads(self.tasks_file.read_text(encoding="utf-8"))

    def test_get_tasks_scans_and_persists_automation_state(self):
        now = datetime.now()
        task = make_task(updated_at=(now - timedelta(hours=49)).isoformat())
        self.write_tasks([task])

        response = self.client.get("/api/tasks")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload[0]["automation"]["state"], ["silent"])
        persisted = self.read_tasks()
        self.assertEqual(persisted[0]["automation"]["state"], ["silent"])

    def test_manual_scan_endpoint_returns_detected_events(self):
        now = datetime.now()
        task = make_task(
            status="done",
            updated_at=(now - timedelta(days=4)).isoformat(),
        )
        self.write_tasks([task])

        response = self.client.post("/api/tasks/automation/scan")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["scanned"], 1)
        self.assertEqual(payload["changed"], 1)
        self.assertEqual(payload["events"][0]["state"], "auto_archived")


if __name__ == "__main__":
    unittest.main()
