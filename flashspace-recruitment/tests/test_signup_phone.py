"""Candidate signup phone field: required, exactly 10 digits.

The phone number is stored in the candidate's workspace profile (personal
section + shared field) so it flows into My Profile and the ClickUp Profile task.
"""
import os
import unittest
from unittest.mock import patch
import test_workspace_server as ws


class SignupPhoneTests(ws.WorkspaceTests):
    def signup_with(self, extra):
        body = {'name': 'Phone Candidate', 'email': 'phone@example.com',
                'password': 'test-password-long', 'confirm_password': 'test-password-long'}
        body.update(extra)
        return self.req('/api/auth/candidate/signup', body)

    def test_valid_phone_saved_to_profile(self):
        r = self.signup_with({'phone': '9876543210'})
        self.assertEqual(r['status'], 200, r)
        # Profile view must show the phone in the personal section and shared fields.
        view = self.req('/api/workspace/candidate/profile')['body']
        self.assertEqual(view['sections']['personal']['phone'], '9876543210')

    def test_empty_phone_is_rejected(self):
        r = self.signup_with({'phone': ''})
        self.assertEqual(r['status'], 400, r)

    def test_missing_phone_field_is_rejected(self):
        r = self.req('/api/auth/candidate/signup', {'name': 'No Phone', 'email': 'nophone@example.com',
                     'password': 'test-password-long', 'confirm_password': 'test-password-long'})
        self.assertEqual(r['status'], 400, r)

    def test_rejects_non_numeric_phone(self):
        r = self.signup_with({'phone': '98765abcde'})
        self.assertEqual(r['status'], 400, r)

    def test_rejects_wrong_length_phone(self):
        for phone in ('987654321', '98765432101', '98-7654-3210', '+919****3210'):
            r = self.signup_with({'phone': phone})
            self.assertEqual(r['status'], 400, phone)

    def test_login_ignores_extra_fields(self):
        self.signup_with({'phone': '9876543210'})
        r = self.req('/api/auth/candidate/login', {'email': 'phone@example.com', 'password': 'test-password-long'})
        self.assertEqual(r['status'], 200, r)


if __name__ == '__main__':
    unittest.main()
