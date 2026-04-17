# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):

    _inherit = 'res.partner'
    # türkçe değişcek
    iys_sms_consent = fields.Selection(
        selection=[('ONAY', 'Approved'),
                   ('RET', 'Rejected'),
                   ('pending', 'Pending')
        ],
        string='IYS SMS Consent (MESAJ)',
        default='pending',
        tracking=True,
    )

    def _iys_consent_items(self):

        items = super()._iys_consent_items()
        items.append((self.verimor_mobile,
                      'MESAJ',
                      self.iys_sms_consent)
         )

        return items

    def _apply_iys_pull(self, consent_type, status):
        """IYS pull: update SMS consent field when Verimor reports a change."""
        # türkçe değişcek
        if consent_type == 'MESAJ':
            self.with_context(iys_skip_push=True).write({'iys_sms_consent': status})

        return super()._apply_iys_pull(consent_type, status)
