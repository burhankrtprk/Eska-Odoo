# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestIysMail(TransactionCase):
    """OCA-standard tests for iys_mass_mailing e-mail consent filtering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Consent = cls.env['iys.consent']
        cls.MailMail = cls.env['mail.mail']
        cls.Partner = cls.env['res.partner']

    def _make_partner(self, name, email, consent_status):
        partner = self.Partner.create({'name': name, 'email': email})
        if consent_status in ('ONAY', 'RET'):
            self.Consent._add(email.lower(), 'EPOSTA', consent_status)
        return partner

    def _make_mail(self, recipients, is_commercial=True):
        return self.MailMail.create({
            'subject': 'Test Mail',
            'body_html': '<p>Hello</p>',
            'email_from': 'noreply@example.com',
            'is_commercial': is_commercial,
            'recipient_ids': [(4, p.id) for p in recipients],
            'state': 'outgoing',
        })

    # ------------------------------------------------------------------ #
    #  is_commercial=True + EPOSTA RET → blocked                          #
    # ------------------------------------------------------------------ #

    def test_commercial_ret_blocked(self):
        """Commercial mail to a single RET partner → state='cancel'."""
        from unittest.mock import patch
        partner = self._make_partner('Ret Partner', 'ret@example.com', 'RET')
        mail = self._make_mail([partner], is_commercial=True)

        with patch(
            'odoo.addons.base.models.ir_mail_server.IrMailServer.send_email',
            return_value='test-msg-id',
        ):
            mail._send()

        self.assertEqual(mail.state, 'cancel')

    def test_commercial_onay_passes(self):
        """Commercial mail to an ONAY partner → remains outgoing (not cancelled)."""
        partner = self._make_partner('Onay Partner', 'onay@example.com', 'ONAY')
        mail = self._make_mail([partner], is_commercial=True)

        # We don't actually send via SMTP; just verify it's not cancelled.
        # Patch smtp to avoid real network call.
        from unittest.mock import patch
        with patch('odoo.addons.base.models.ir_mail_server.IrMailServer.send_email', return_value='test-msg-id'):
            mail._send()

        self.assertNotEqual(mail.state, 'cancel')

    def test_non_commercial_bypass(self):
        """Non-commercial mail to a RET partner is NOT blocked."""
        partner = self._make_partner('Ret2 Partner', 'ret2@example.com', 'RET')
        mail = self._make_mail([partner], is_commercial=False)

        mail._send()

        # Not cancelled – non-commercial bypasses IYS check
        self.assertNotEqual(mail.state, 'cancel')

    def test_partial_recipients(self):
        """1 ONAY + 1 RET → RET partner dropped, mail not cancelled."""
        onay = self._make_partner('Onay2', 'onay2@example.com', 'ONAY')
        ret = self._make_partner('Ret3', 'ret3@example.com', 'RET')
        mail = self._make_mail([onay, ret], is_commercial=True)

        from unittest.mock import patch
        with patch('odoo.addons.base.models.ir_mail_server.IrMailServer.send_email', return_value='test-msg-id'):
            mail._send()

        # Mail should not be cancelled (ONAY partner still allowed)
        self.assertNotEqual(mail.state, 'cancel')
        # Blocked partner removed from recipients
        self.assertNotIn(ret, mail.recipient_ids)

    # ------------------------------------------------------------------ #
    #  mailing.mailing opt-out list                                        #
    # ------------------------------------------------------------------ #

    def test_mailing_opt_out_list(self):
        """IYS EPOSTA RET entries appear in mailing _get_opt_out_list()."""
        self.Consent._add('blocked@example.com', 'EPOSTA', 'RET')

        mailing = self.env['mailing.mailing'].create({
            'subject': 'Opt-out test',
            'mailing_model_id': self.env.ref('base.model_res_partner').id,
            'body_html': '<p>Test</p>',
        })
        opt_out = mailing._get_opt_out_list()
        self.assertIn('blocked@example.com', opt_out)

    def test_blacklist_sync_to_iys(self):
        """Adding to mail.blacklist → iys.consent EPOSTA set to RET."""
        email = 'unsub@example.com'
        self.env['mail.blacklist']._add([email])
        status = self.Consent._lookup(email, 'EPOSTA')
        self.assertEqual(status, 'RET')

    def test_blacklist_remove_syncs_onay(self):
        """Removing from mail.blacklist → iys.consent EPOSTA set to ONAY."""
        email = 'resub@example.com'
        self.env['mail.blacklist']._add([email])
        self.env['mail.blacklist']._remove(email)
        status = self.Consent._lookup(email, 'EPOSTA')
        self.assertEqual(status, 'ONAY')
