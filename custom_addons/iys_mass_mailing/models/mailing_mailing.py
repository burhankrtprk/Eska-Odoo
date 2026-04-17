# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class MailingMailing(models.Model):
    _inherit = 'mailing.mailing'

    def _get_opt_out_list(self):
        """
        Extend the opt-out list with IYS EPOSTA-rejected e-mail addresses.

        Odoo's mass mailing uses this to exclude recipients before sending.
        We add all e-mail addresses that have an active iys.consent record
        with consent_type='EPOSTA' and status='RET'.
        """

        opt_out = super()._get_opt_out_list()
        # türkçe değişcek
        # Fetch all EPOSTA-rejected addresses from the consent store
        blocked = self.env['iys.consent'].with_context(active_test=False).search([
            ('consent_type', '=', 'EPOSTA'),
            ('status', '=', 'RET'),
        ])

        iys_opt_out = set(blocked.mapped('recipient'))

        if iys_opt_out:
            _logger.debug(
                'iys_mass_mailing: adding %d IYS EPOSTA-blocked addresses to opt-out list',
                len(iys_opt_out),
            )

        return opt_out | iys_opt_out
