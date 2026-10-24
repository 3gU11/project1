import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import contract_drafts, auth


class ContractRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(contract_drafts.router, prefix='/contracts')
        app.dependency_overrides[auth.get_current_user_context] = lambda: {'username': 'real-supervisor', 'role': 'reviewer'}
        self.client = TestClient(app)
        self.permissions = patch.object(auth, 'get_role_permissions', return_value=['DEALER_ORDER_REVIEW'])
        self.permissions.start()

    def tearDown(self):
        self.permissions.stop()
        self.client.close()

    def test_reviewer_is_taken_from_authenticated_context_not_request(self):
        with patch.object(contract_drafts.bridge, 'review', return_value={'state': 'approved'}) as review:
            response = self.client.post('/contracts/12345678-1234-1234-1234-123456789abc/review', json={'previewHash': 'a'*64, 'decision': 'approved', 'reviewer': 'forged-admin'})
            self.assertEqual(200, response.status_code)
            self.assertEqual('real-supervisor', review.call_args.args[3])

    def test_permission_and_rejection_reason_are_enforced(self):
        url='/contracts/12345678-1234-1234-1234-123456789abc/review'
        payload={'previewHash': 'a'*64, 'decision': 'rejected'}
        self.assertEqual(422, self.client.post(url,json=payload).status_code)
        with patch.object(auth, 'get_role_permissions', return_value=[]):
            self.assertEqual(403, self.client.get('/contracts').status_code)


if __name__ == '__main__':
    unittest.main()
