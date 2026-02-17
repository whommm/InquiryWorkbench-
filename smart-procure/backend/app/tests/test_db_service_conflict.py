import os
import sys
import unittest
from datetime import timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_dbservice_conflict.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.core.datetime_utils import ensure_utc, utc_now  # noqa: E402
from app.models.database import InquirySheet, SessionLocal, User, init_db  # noqa: E402
from app.services.db_service import DBService, SheetConflictError  # noqa: E402


class TestDBServiceConflict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.user_id = "conflict-test-user"
        user = self.db.query(User).filter(User.id == self.user_id).first()
        if not user:
            self.db.add(
                User(
                    id=self.user_id,
                    username="conflict_test_user",
                    password_hash="hash",
                    display_name="conflict_test_user",
                    role="user",
                )
            )
            self.db.commit()
        self.service = DBService(self.db)

    def tearDown(self):
        self.db.query(InquirySheet).filter(InquirySheet.user_id == self.user_id).delete()
        self.db.query(User).filter(User.id == self.user_id).delete()
        self.db.commit()
        self.db.close()

    def _create_sheet(self, sheet_id: str = "sheet-conflict-1") -> InquirySheet:
        return self.service.save_sheet(
            sheet_id=sheet_id,
            name="test",
            sheet_data=[["列"], ["值"]],
            chat_history=[],
            user_id=self.user_id,
            item_count=1,
            completion_rate=0.0,
            expected_updated_at=None,
            force_overwrite=True,
        )

    def test_save_requires_base_version_when_existing_sheet(self):
        self._create_sheet()
        with self.assertRaises(SheetConflictError) as ctx:
            self.service.save_sheet(
                sheet_id="sheet-conflict-1",
                name="changed",
                sheet_data=[["列"], ["新值"]],
                chat_history=[],
                user_id=self.user_id,
                item_count=1,
                completion_rate=0.0,
                expected_updated_at=None,
                force_overwrite=False,
            )
        self.assertEqual(ctx.exception.reason, "missing_base")

    def test_save_rejects_stale_base_version(self):
        created = self._create_sheet()
        stale_base = ensure_utc(created.updated_at) - timedelta(seconds=1)
        with self.assertRaises(SheetConflictError) as ctx:
            self.service.save_sheet(
                sheet_id="sheet-conflict-1",
                name="changed",
                sheet_data=[["列"], ["新值"]],
                chat_history=[],
                user_id=self.user_id,
                item_count=1,
                completion_rate=0.0,
                expected_updated_at=stale_base,
                force_overwrite=False,
            )
        self.assertEqual(ctx.exception.reason, "stale_base")

    def test_save_accepts_equal_or_newer_base_version(self):
        created = self._create_sheet()
        saved = self.service.save_sheet(
            sheet_id="sheet-conflict-1",
            name="changed",
            sheet_data=[["列"], ["新值"]],
            chat_history=[],
            user_id=self.user_id,
            item_count=1,
            completion_rate=0.0,
            expected_updated_at=ensure_utc(created.updated_at),
            force_overwrite=False,
        )
        self.assertEqual(saved.name, "changed")
        self.assertGreaterEqual(ensure_utc(saved.updated_at), ensure_utc(created.updated_at))

    def test_force_overwrite_bypasses_conflict(self):
        created = self._create_sheet()
        stale_base = ensure_utc(created.updated_at) - timedelta(days=1)
        saved = self.service.save_sheet(
            sheet_id="sheet-conflict-1",
            name="forced",
            sheet_data=[["列"], ["覆盖"]],
            chat_history=[],
            user_id=self.user_id,
            item_count=1,
            completion_rate=0.0,
            expected_updated_at=stale_base,
            force_overwrite=True,
        )
        self.assertEqual(saved.name, "forced")


if __name__ == "__main__":
    unittest.main()

