# -*- coding: utf-8 -*-
import logging
from odoo import fields, models
from odoo.addons.iys.models.res_partner import _normalize_phone

_logger = logging.getLogger(__name__)

# Context key set by transactional (non-commercial) callers to bypass IYS check.
_CTX_TRANSACTIONAL = 'iys_transactional_sms'


class SmsSms(models.Model):

    _inherit = 'sms.sms'


    #override _send method through odoo native sms module
    def _send(self,
              unlink_failed=False,
              unlink_sent=True,
              raise_exception=False,
      ):
        """
        Override _send() to block outgoing SMS for IYS-rejected recipients.

        Transactional SMS (context key 'iys_transactional_sms=True') bypass the check.
        """

        if self.env.context.get(_CTX_TRANSACTIONAL):

            return super()._send(
                unlink_failed=unlink_failed,
                unlink_sent=unlink_sent,
                raise_exception=raise_exception,
            )

        Consent = self.env['iys.consent']
        blocked = self.env['sms.sms']
        allowed = self.env['sms.sms']

        for sms in self:
            number = sms.number or ''
            # Normalise to E.164 for lookup
            normalized = _normalize_phone(number) or number
            # türkçe değişcek
            if Consent._is_blocked(normalized,
                                   'MESAJ',
            ):
                # türkçe değişcek
                _logger.info(
                    'iys_sms: SMS to %s blocked – IYS MESAJ consent is RET',
                    number,
                )
                blocked |= sms

            else:
                allowed |= sms

        # Mark blocked messages as failed

        if blocked:
            blocked.write({
                'state': 'error',
                'failure_type': 'sms_blacklist',
            })

        if allowed:

            return super(SmsSms, allowed)._send(
                unlink_failed=unlink_failed,
                unlink_sent=unlink_sent,
                raise_exception=raise_exception,
            )

        return True
