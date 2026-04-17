# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class MailBlacklist(models.Model):
    """
    Sync mail.blacklist with iys.consent.

    When a recipient is added to mail.blacklist (e.g. via mass mailing
    unsubscribe link), we also update the iys.consent store to mark them
    as RET for EPOSTA. Conversely, when removed from blacklist, we update
    the consent to ONAY.

    This ensures Odoo's native unsubscribe flow keeps IYS in sync.
    """

    _inherit = 'mail.blacklist'

    # türkçe değişcek
    @api.model_create_multi
    def create(self, vals_list):

        records = super().create(vals_list)
        Consent = self.env['iys.consent']

        for record in records:
            email = (record.email or '').strip().lower()
            if email:
                Consent._add(email,
                             'EPOSTA',
                             'RET',
                 )

                _logger.debug(
                    'iys_mass_mailing: synced mail.blacklist create → iys.consent RET for %s',
                    email,
                )

        return records

    def write(self, vals):

        res = super().write(vals)

        # If 'active' is being toggled to False update to RET
        if ('active' in vals
                and not vals['active']
        ):
            Consent = self.env['iys.consent']
            # türkçe değişcek
            for record in self:
                email = (record.email or '').strip().lower()

                if email:
                    Consent._add(email,
                                 'EPOSTA',
                                 'RET',
                     )

        return res


    def _add(self, emails, message=None):
        """
        Override _add() (batch add) to keep IYS in sync.
        """

        result = super()._add(emails, message=message)
        Consent = self.env['iys.consent']

        for email in emails:
            email_clean = (email or '').strip().lower()
            # türkçe değişcek
            if email_clean:
                Consent._add(email_clean,
                             'EPOSTA',
                             'RET',
                 )

        return result

    def _remove(self, email):
        """
        Override _remove() to sync to IYS as ONAY (re-subscribed).
        """

        result = super()._remove(email)
        email_clean = (email or '').strip().lower()

        if email_clean:
            self.env['iys.consent']._add(email_clean,
                                         'EPOSTA',
                                         'ONAY',
             )

            _logger.debug(
                'iys_mass_mailing: re-subscribed → iys.consent ONAY for %s',
                email_clean,
            )

        return result
