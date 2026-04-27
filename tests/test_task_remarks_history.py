import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def make_task(**overrides):
    task = {
        "id": 1,
        "title": "T",
        "description": "",
        "status": "pending",
        "priority": "medium",
        "due_date": None,
        "source": "",
        "sender": "",
        "raw_text": "",
        "created_at": "2026-04-01T10:00:00",
        "updated_at": "2026-04-01T10:00:00",
    }
    task.update(overrides)
    return task


class TaskRemarksHistoryTest(unittest.TestCase):
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

    def test_create_task_has_initial_status_history(self):
        self.write_tasks([])
        r = self.client.post(
            "/api/tasks",
            json={"title": "A", "description": "", "remarks": "  note  "},
        )
        self.assertEqual(r.status_code, 201)
        body = r.get_json()
        self.assertEqual(body["remarks"], "note")
        self.assertEqual(len(body["status_history"]), 1)
        self.assertIsNone(body["status_history"][0]["from"])
        self.assertEqual(body["status_history"][0]["to"], "pending")

    def test_put_status_appends_history(self):
        self.write_tasks([make_task()])
        r = self.client.put("/api/tasks/1", json={"status": "in_progress"})
        self.assertEqual(r.status_code, 200)
        h = r.get_json()["status_history"]
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["from"], "pending")
        self.assertEqual(h[0]["to"], "in_progress")

        r2 = self.client.put("/api/tasks/1", json={"status": "pending"})
        self.assertEqual(r2.status_code, 200)
        h2 = r2.get_json()["status_history"]
        self.assertEqual(len(h2), 2)
        self.assertEqual(h2[1]["from"], "in_progress")
        self.assertEqual(h2[1]["to"], "pending")

    def test_put_remarks_without_status_change(self):
        self.write_tasks([make_task()])
        r = self.client.put("/api/tasks/1", json={"remarks": "done step 1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["remarks"], "done step 1")
        self.assertEqual(r.get_json()["status_history"], [])

    def test_task_to_dict_legacy_task_without_fields(self):
        t = make_task()
        d = app.task_to_dict(t)
        self.assertEqual(d["remarks"], "")
        self.assertEqual(d["status_history"], [])


if __name__ == "__main__":
    unittest.main()
