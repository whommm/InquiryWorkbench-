import os
import sys
import unittest
import asyncio

from fastapi import HTTPException, status

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_auth.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.auth.utils import is_admin_user, require_admin_user  # noqa: E402


class DummyUser:
    def __init__(self, role):
        self.role = role


class TestAdminAuth(unittest.TestCase):
    def test_is_admin_user_true(self):
        self.assertTrue(is_admin_user(DummyUser("admin")))
        self.assertTrue(is_admin_user(DummyUser("ADMIN")))

    def test_is_admin_user_false(self):
        self.assertFalse(is_admin_user(DummyUser("user")))
        self.assertFalse(is_admin_user(DummyUser(None)))

    def test_require_admin_user_forbidden(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(require_admin_user(DummyUser("user")))
        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)

    def test_require_admin_user_ok(self):
        user = asyncio.run(require_admin_user(DummyUser("admin")))
        self.assertEqual(user.role, "admin")


if __name__ == "__main__":
    unittest.main()

