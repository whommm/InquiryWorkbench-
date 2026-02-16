import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_notifications.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.models.database import init_db, SessionLocal, User  # noqa: E402
from app.services.notification_service import add_notification, pop_notifications  # noqa: E402


class TestNotificationService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        user = self.db.query(User).filter(User.id == "user-test-1").first()
        if not user:
            self.db.add(
                User(
                    id="user-test-1",
                    username="notif_test_user",
                    password_hash="hash",
                    display_name="notif_test_user",
                    role="user",
                )
            )
            self.db.commit()

    def tearDown(self):
        self.db.query(User).filter(User.id == "user-test-1").delete()
        self.db.commit()
        self.db.close()

    def test_pop_notifications_returns_and_clears(self):
        add_notification("user-test-1", "n1", "info")
        add_notification("user-test-1", "n2", "success")

        notifications = pop_notifications(self.db, "user-test-1")
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0]["message"], "n1")
        self.assertEqual(notifications[1]["type"], "success")

        again = pop_notifications(self.db, "user-test-1")
        self.assertEqual(again, [])


if __name__ == "__main__":
    unittest.main()

