import unittest
from unittest.mock import patch
from fastapi import HTTPException
from api.upload_guard import require_uploads_enabled


class UploadGuardTests(unittest.TestCase):
    def test_uploads_are_disabled_by_default(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                require_uploads_enabled()
        self.assertEqual(503, raised.exception.status_code)

    def test_uploads_can_be_temporarily_reenabled_by_environment_switch(self):
        with patch.dict('os.environ', {'V8_UPLOADS_ENABLED': 'true'}, clear=True):
            self.assertIsNone(require_uploads_enabled())


if __name__ == '__main__':
    unittest.main()
