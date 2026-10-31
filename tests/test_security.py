import os
import sys
import unittest
from fastapi import HTTPException

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.config import settings
from app.core.security import create_player_token, verify_player_token, verify_admin_key


class TestSecurity(unittest.TestCase):
    def test_player_jwt_token_generation_and_validation(self):
        user_id = "pilot_44"
        driver_name = "Hamilton"

        # 1. Generate valid token
        token = create_player_token(user_id, driver_name)
        self.assertIsInstance(token, str)

        # 2. Verify token payload
        payload = verify_player_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], user_id)
        self.assertEqual(payload["name"], driver_name)

        # 3. Tampered token should return None
        tampered_token = token[:-5] + "XXXXX"
        self.assertIsNone(verify_player_token(tampered_token))

    def test_admin_key_verification(self):
        # 1. Correct admin key passes
        self.assertTrue(verify_admin_key(x_admin_key=settings.ADMIN_API_KEY))

        # 2. Incorrect key raises 401
        with self.assertRaises(HTTPException) as ctx:
            verify_admin_key(x_admin_key="wrong_password")
        self.assertEqual(ctx.exception.status_code, 401)

        # 3. Missing key raises 401
        with self.assertRaises(HTTPException) as ctx:
            verify_admin_key(x_admin_key=None, auth=None)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()

