# -*- coding: utf-8 -*-
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    iys_call_consent = fields.Selection(
        selection=[('ONAY', 'Approved'),
                   ('RET', 'Rejected'),
                   ('pending', 'Pending')
         ],
        string='IYS Call Consent (ARAMA)',
        default='pending',
        tracking=True,
    )

    def _iys_consent_items(self):
        items = super()._iys_consent_items()
        items.append((self.verimor_mobile,
                      'ARAMA',
                      self.iys_call_consent)
         )

        return items
#türkçe değişecek
    def _apply_iys_pull(self, consent_type, status):
        """IYS pull: update Voice Call consent field when Verimor reports a change."""

        if consent_type == 'ARAMA':
            self.with_context(iys_skip_push=True).write({'iys_call_consent': status})

        return super()._apply_iys_pull(consent_type, status)
