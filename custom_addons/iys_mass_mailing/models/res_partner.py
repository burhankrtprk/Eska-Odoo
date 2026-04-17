# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'
    # türkçe değişcek
    iys_email_consent = fields.Selection(
        selection=[('ONAY', 'Approved'),
                   ('RET', 'Rejected'),
                   ('pending', 'Pending')
        ],
        string='IYS Email Consent (EPOSTA)',
        default='pending',
        tracking=True,
    )

    def _iys_consent_items(self):
        # türkçe değişcek
        items = super()._iys_consent_items()
        items.append((self.email,
                      'EPOSTA',
                      self.iys_email_consent)
         )

        return items

    def _apply_iys_pull(self, consent_type, status):
        """IYS pull: update Email consent field when Verimor reports a change."""
        # türkçe değişcek
        if consent_type == 'EPOSTA':
            self.with_context(iys_skip_push=True).write({'iys_email_consent': status})

        return super()._apply_iys_pull(consent_type, status)
