import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_admin_progress.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.core.datetime_utils import utc_now  # noqa: E402
from app.models.columns import (  # noqa: E402
    ITEM_COL_BRAND,
    ITEM_COL_NAME,
    ITEM_COL_SPEC,
    SLOT_FIELD_PRICE,
    SLOT_TEMPLATE,
)
from app.models.database import InquirySheet, SessionLocal, User, init_db  # noqa: E402
from app.services.admin_progress_service import (  # noqa: E402
    get_overview_daily_progress,
    get_user_daily_progress,
)


class TestAdminProgressService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.db.query(InquirySheet).delete()
        self.db.query(User).delete()
        self.db.commit()

        self.user_1 = User(
            id="user-progress-1",
            username="progress_user_1",
            password_hash="hash",
            display_name="User 1",
            role="user",
        )
        self.user_2 = User(
            id="user-progress-2",
            username="progress_user_2",
            password_hash="hash",
            display_name="User 2",
            role="user",
        )
        self.db.add_all([self.user_1, self.user_2])
        self.db.commit()

    def tearDown(self):
        self.db.query(InquirySheet).delete()
        self.db.query(User).delete()
        self.db.commit()
        self.db.close()

    def _make_sheet_data(self, quoted_first_row: bool) -> list:
        headers = [ITEM_COL_NAME, ITEM_COL_BRAND, ITEM_COL_SPEC]
        for slot in range(1, 4):
            for field in SLOT_TEMPLATE:
                headers.append(f"{field}{slot}")

        row_1 = ["产品A", "品牌A", "A-100"] + [None] * (len(headers) - 3)
        row_2 = ["产品B", "品牌A", "B-200"] + [None] * (len(headers) - 3)

        price_idx_slot1 = headers.index(f"{SLOT_FIELD_PRICE}1")
        if quoted_first_row:
            row_1[price_idx_slot1] = 123.0

        return [headers, row_1, row_2]

    def test_overview_aggregates_rows_and_progress(self):
        now = utc_now()
        self.db.add(
            InquirySheet(
                id="sheet-1",
                user_id=self.user_1.id,
                name="Sheet 1",
                sheet_data=self._make_sheet_data(quoted_first_row=True),
                chat_history=[],
                item_count=2,
                completion_rate=0.5,
                updated_at=now,
            )
        )
        self.db.add(
            InquirySheet(
                id="sheet-2",
                user_id=self.user_2.id,
                name="Sheet 2",
                sheet_data=self._make_sheet_data(quoted_first_row=False),
                chat_history=[],
                item_count=2,
                completion_rate=0.0,
                updated_at=now,
            )
        )
        self.db.commit()

        overview = get_overview_daily_progress(self.db, tz_name="UTC")
        self.assertEqual(overview["kpis"]["active_user_count"], 2)
        self.assertEqual(overview["kpis"]["updated_sheet_count"], 2)
        self.assertEqual(overview["kpis"]["total_rows"], 4)
        self.assertEqual(overview["kpis"]["quoted_rows"], 1)

    def test_user_detail_contains_sheet_breakdown(self):
        now = utc_now()
        self.db.add(
            InquirySheet(
                id="sheet-3",
                user_id=self.user_1.id,
                name="Sheet 3",
                sheet_data=self._make_sheet_data(quoted_first_row=True),
                chat_history=[],
                item_count=2,
                completion_rate=0.5,
                updated_at=now,
            )
        )
        self.db.commit()

        detail = get_user_daily_progress(self.db, user_id=self.user_1.id, tz_name="UTC")
        self.assertIsNotNone(detail["user"])
        self.assertEqual(detail["user"]["today_total_rows"], 2)
        self.assertEqual(detail["user"]["today_quoted_rows"], 1)
        self.assertEqual(len(detail["sheets"]), 1)


if __name__ == "__main__":
    unittest.main()
