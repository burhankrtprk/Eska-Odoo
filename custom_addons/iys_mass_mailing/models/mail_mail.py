# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MailMail(models.Model):

    _inherit = 'mail.mail'

    is_commercial = fields.Boolean(
        string='Commercial Message',
        default=False,
        help='Mark as True for marketing/commercial e-mails that require IYS consent check.',
    )

    def _send(self,
              auto_commit=False,
              raise_exception=False,
              smtp_session=None,
              alias_domain_id=False,
      ):

        """
        Override _send() to block commercial e-mail for IYS EPOSTA-rejected recipients.

        Non-commercial (is_commercial=False) e-mails bypass this check entirely.
        Covers both partner-linked recipients (recipient_ids) and raw email_to strings.
        """

        Consent = self.env['iys.consent']

        for mail in self:
            if not mail.is_commercial:
                continue

            # --- partner-linked recipients ---
            blocked_partners = mail.recipient_ids.filtered(
                lambda p: Consent._is_blocked(p.email or '',
                                              'EPOSTA',
                )
            )

            if blocked_partners:
                allowed_partners = mail.recipient_ids - blocked_partners

                _logger.info(
                    'iys_mass_mailing: commercial mail %s – blocked %d partner recipient(s), allowed %d',
                    mail.id,
                    len(blocked_partners),
                    len(allowed_partners),
                )

                mail.write({'recipient_ids': [(3, p.id) for p in blocked_partners]})

            # --- raw email_to string (non-partner addresses) ---
            if mail.email_to:

                raw_addresses = [a.strip() for a in mail.email_to.split(',') if a.strip()]

                allowed_addresses = [
                    a for a in raw_addresses
                    # türkçe değişcek
                    if not Consent._is_blocked(a.lower(),
                                               'EPOSTA',
                    )
                ]

                blocked_count = len(raw_addresses) - len(allowed_addresses)

                if blocked_count:
                    _logger.info(
                        'iys_mass_mailing: commercial mail %s – blocked %d email_to address(es)',
                        mail.id, blocked_count,
                    )

                    mail.write({'email_to': ', '.join(allowed_addresses) if allowed_addresses else False})

            # If ALL recipients were removed, cancel the mail
            if not mail.recipient_ids and not mail.email_to:
                mail.write({
                    'state': 'cancel',
                    'failure_reason': self.env._(
                        'All recipients have rejected IYS e-mail consent. Commercial e-mail blocked.'
                    ),
                })

        remaining = self.filtered(lambda m: m.state == 'outgoing')

        if remaining:
            return super(MailMail, remaining)._send(
                auto_commit=auto_commit,
                raise_exception=raise_exception,
                smtp_session=smtp_session,
                alias_domain_id=alias_domain_id,
            )

        return True
