# -*- coding: utf-8 -*-
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.addons.iys.models.res_partner import _normalize_phone


class TestIysConsent(TransactionCase):
    """OCA-standard tests for iys.consent model and partner IYS logic."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Consent = cls.env['iys.consent']
        cls.Partner = cls.env['res.partner']

    # ------------------------------------------------------------------ #
    #  iys.consent._add / _remove / _lookup                               #
    # ------------------------------------------------------------------ #

    def test_consent_add_ret(self):
        """_add() with RET status → active=False."""
        record = self.Consent._add('905301234567', 'MESAJ', 'RET')
        self.assertEqual(record.status, 'RET')
        self.assertFalse(record.active)

    def test_consent_add_onay(self):
        """_add() with ONAY status → active=True."""
        record = self.Consent._add('905301234568', 'ARAMA', 'ONAY')
        self.assertEqual(record.status, 'ONAY')
        self.assertTrue(record.active)

    def test_consent_pending(self):
        """_lookup() without a record → returns 'pending'."""
        status = self.Consent._lookup('905399999999', 'EPOSTA')
        self.assertEqual(status, 'pending')

    def test_consent_update_existing(self):
        """_add() called twice on same recipient/type updates existing record."""
        self.Consent._add('905301111111', 'MESAJ', 'ONAY')
        self.Consent._add('905301111111', 'MESAJ', 'RET')
        records = self.Consent.with_context(active_test=False).search([
            ('recipient', '=', '905301111111'),
            ('consent_type', '=', 'MESAJ'),
        ])
        self.assertEqual(len(records), 1)
        self.assertEqual(records.status, 'RET')

    def test_consent_remove(self):
        """_remove() deletes the record; _lookup() returns 'pending' afterwards."""
        self.Consent._add('905302222222', 'EPOSTA', 'ONAY')
        self.Consent._remove('905302222222', 'EPOSTA')
        self.assertEqual(self.Consent._lookup('905302222222', 'EPOSTA'), 'pending')

    def test_is_blocked(self):
        """_is_blocked() returns True only when status=RET."""
        self.Consent._add('905303333333', 'ARAMA', 'RET')
        self.assertTrue(self.Consent._is_blocked('905303333333', 'ARAMA'))
        self.assertFalse(self.Consent._is_blocked('905303333333', 'MESAJ'))

    # ------------------------------------------------------------------ #
    #  _normalize_phone helper                                             #
    # ------------------------------------------------------------------ #

    def test_normalize_phone_local(self):
        """'05301234567' normalises to '905301234567'."""
        self.assertEqual(_normalize_phone('05301234567'), '905301234567')

    def test_normalize_phone_plus90(self):
        """'+905301234567' normalises to '905301234567'."""
        self.assertEqual(_normalize_phone('+905301234567'), '905301234567')

    def test_normalize_phone_invalid(self):
        """Landline numbers return None."""
        self.assertIsNone(_normalize_phone('02121234567'))

    def test_normalize_phone_none(self):
        """None input returns None."""
        self.assertIsNone(_normalize_phone(None))

    # ------------------------------------------------------------------ #
    #  _build_iys_consents payload                                         #
    # ------------------------------------------------------------------ #

    def test_build_iys_consents_payload(self):
        """_build_iys_consents() returns correct MESAJ/ARAMA/EPOSTA entries."""
        partner = self.Partner.create({
            'name': 'Test IYS',
            'mobile': '05301234567',
            'email': 'test@example.com',
        })

        def dummy_items(self):
            return [
                ('905301234567', 'MESAJ', 'ONAY'),
                ('905301234567', 'ARAMA', 'RET'),
                ('test@example.com', 'EPOSTA', 'ONAY'),
            ]

        with patch('odoo.addons.iys.models.res_partner.ResPartner._iys_consent_items', dummy_items):
            consents = partner._build_iys_consents()
            types = {c['type'] for c in consents}
            self.assertIn('MESAJ', types)
            self.assertIn('ARAMA', types)
            self.assertIn('EPOSTA', types)

            mesaj = next(c for c in consents if c['type'] == 'MESAJ')
            self.assertEqual(mesaj['status'], 'ONAY')
            self.assertEqual(mesaj['recipient'], '905301234567')

            arama = next(c for c in consents if c['type'] == 'ARAMA')
            self.assertEqual(arama['status'], 'RET')

    def test_build_iys_consents_pending_excluded(self):
        """Pending consents are not included in the payload."""
        partner = self.Partner.create({
            'name': 'Pending Partner',
            'mobile': '05309999999',
        })

        def dummy_items(self):
            return [('90530999999', 'MESAJ', 'pending')]

        with patch('odoo.addons.iys.models.res_partner.ResPartner._iys_consent_items', dummy_items):
            consents = partner._build_iys_consents()
            self.assertEqual(consents, [])

    # ------------------------------------------------------------------ #
    #  _push_iys_consents HTTP call                                        #
    # ------------------------------------------------------------------ #

    def test_push_iys_consents_called_after_write(self):
        """write() on IYS fields triggers _push_iys_consents() and enqueues payload."""
        from odoo import fields
        partner = self.Partner.create({
            'name': 'Push Test',
            'mobile': '05301234561',
        })

        account = self.env['iap.account'].create({
            'name': 'IYS Test Account',
            'provider': 'iys_verimor',
            'iys_username': 'testuser',
            'iys_password': 'testpass',
            'iys_source_addr': 'TESTFIRMA',
        })

        def dummy_items(self):
            return [('905301234561', 'MESAJ', 'ONAY')]

        with patch('odoo.addons.iys.models.res_partner.ResPartner._iys_consent_items', dummy_items):
            queue_before = self.env['iys.push.queue'].search_count([('partner_id', '=', partner.id)])
            self.assertEqual(queue_before, 0)

            partner.write({'iys_consent_date': fields.Datetime.now()})

            queue_item = self.env['iys.push.queue'].search([('partner_id', '=', partner.id)])
            self.assertEqual(len(queue_item), 1)
            self.assertEqual(queue_item.state, 'pending')

        # cleanup
        account.unlink()
