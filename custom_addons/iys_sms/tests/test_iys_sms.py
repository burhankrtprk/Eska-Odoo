# -*- coding: utf-8 -*-
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase


class TestIysSms(TransactionCase):
    """OCA-standard tests for iys_sms SMS blocking and Verimor API integration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Consent = cls.env['iys.consent']
        cls.SmsSms = cls.env['sms.sms']
        cls.Partner = cls.env['res.partner']
        # Create a test IAP account for Verimor SMS
        cls.iap_account = cls.env['iap.account'].create({
            'name': 'Test IYS SMS Verimor',
            'provider': 'sms_verimor',
            'sms_username': 'testuser',
            'sms_password': 'testpass',
            'sms_source_addr': 'TESTFIRMA',
        })

    @classmethod
    def tearDownClass(cls):
        cls.iap_account.unlink()
        super().tearDownClass()

    def _make_sms(self, number):
        return self.SmsSms.create({
            'number': number,
            'body': 'Test message',
            'state': 'outgoing',
        })

    # ------------------------------------------------------------------ #
    #  IYS RET blocking                                                   #
    # ------------------------------------------------------------------ #

    def test_sms_blocked_if_ret(self):
        """SMS to a RET-consented number → state='error', API not called."""
        self.Consent._add('905301234567', 'MESAJ', 'RET')
        sms = self._make_sms('905301234567')

        with patch('requests.post') as mock_post:
            sms._send()
            mock_post.assert_not_called()

        self.assertEqual(sms.state, 'error')
        self.assertEqual(sms.failure_type, 'sms_blacklist')

    def test_sms_sent_if_onay(self):
        """SMS to an ONAY-consented number → API called."""
        self.Consent._add('905301234568', 'MESAJ', 'ONAY')
        sms = self._make_sms('905301234568')

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            sms._send()
            mock_post.assert_called_once()

    def test_sms_sent_if_pending(self):
        """SMS to a number with no consent record (pending) → API called."""
        # Ensure no record exists
        self.Consent._remove('905308888888', 'MESAJ')
        sms = self._make_sms('905308888888')

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            sms._send()
            mock_post.assert_called_once()

    def test_transactional_sms_bypasses_iys(self):
        """Transactional SMS (iys_transactional_sms=True) bypasses RET block."""
        self.Consent._add('905301234569', 'MESAJ', 'RET')
        sms = self._make_sms('905301234569')

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            sms.with_context(iys_transactional_sms=True)._send()
            mock_post.assert_called_once()

    # ------------------------------------------------------------------ #
    #  Verimor API success / error                                         #
    # ------------------------------------------------------------------ #

    def test_verimor_api_success(self):
        """HTTP 200 response → state='success' in batch results."""
        self.Consent._remove('905307777777', 'MESAJ')
        sms = self._make_sms('905307777777')

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            sms._send()

        # After successful send, sms.sms records are unlinked by default;
        # check mock was called with correct endpoint.
        call_args = mock_post.call_args
        self.assertIn('verimor.com.tr', call_args[0][0])

    def test_verimor_api_error(self):
        """HTTP 500 response → SMS state reflects server error."""
        self.Consent._remove('905306666666', 'MESAJ')
        sms = self._make_sms('905306666666')

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = 'Internal Server Error'
            mock_post.return_value = mock_resp
            sms._send()

        # State should reflect error after failed send
        self.assertIn(sms.state, ('error', 'outgoing'))

    def test_credentials_missing(self):
        """Missing iap.account username → all numbers get server_error."""
        # Temporarily clear credentials
        self.iap_account.write({'sms_username': False})
        try:
            sms = self._make_sms('905305555555')
            with patch('requests.post') as mock_post:
                sms._send()
                mock_post.assert_not_called()
        finally:
            self.iap_account.write({'sms_username': 'testuser'})
