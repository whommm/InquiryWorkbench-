import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_notifications.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.models.database import Notification, SessionLocal, User, init_db  # noqa: E402
from app.services.notification_service import (  # noqa: E402
    STATUS_ARCHIVED,
    STATUS_READ,
    STATUS_UNREAD,
    add_notification,
    archive_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    pop_notifications,
)


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
        self.db.query(Notification).filter(Notification.user_id == "user-test-1").delete()
        self.db.query(User).filter(User.id == "user-test-1").delete()
        self.db.commit()
        self.db.close()

    def test_list_notifications_and_read_flow(self):
        add_notification("user-test-1", "n1", "info")
        add_notification("user-test-1", "n2", "success")

        notifications = list_notifications(self.db, "user-test-1", status=STATUS_UNREAD)
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0]["status"], STATUS_UNREAD)

        first_id = notifications[0]["id"]
        marked = mark_notification_read(self.db, "user-test-1", first_id)
        self.assertIsNotNone(marked)
        self.assertEqual(marked["status"], STATUS_READ)

        changed = mark_all_notifications_read(self.db, "user-test-1")
        self.assertGreaterEqual(changed, 1)

    def test_archive_notification(self):
        created = add_notification("user-test-1", "to-archive", "info")
        self.assertIsNotNone(created)

        archived = archive_notification(self.db, "user-test-1", created["id"])
        self.assertIsNotNone(archived)
        self.assertEqual(archived["status"], STATUS_ARCHIVED)

    def test_pop_notifications_marks_as_read(self):
        add_notification("user-test-1", "n1", "info")
        add_notification("user-test-1", "n2", "success")

        notifications = pop_notifications(self.db, "user-test-1")
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0]["status"], STATUS_READ)

        again = pop_notifications(self.db, "user-test-1")
        self.assertEqual(again, [])


if __name__ == "__main__":
    unittest.main()
