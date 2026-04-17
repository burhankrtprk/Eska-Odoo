# -*- coding: utf-8 -*-
import logging
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.addons.iys.models.res_partner import _normalize_phone

_logger = logging.getLogger(__name__)


class VoipCall(models.Model):
    """
    Extend voip.call to block outgoing calls for IYS ARAMA-rejected numbers.

    The check is applied at creation time (create_and_format is the standard
    Odoo entry point for the softphone's "dial" action).
    """
    _inherit = 'voip.call'

    bulutsantralim_call_id = fields.Char(
        string='Bulutsantralim Call ID',
        index=True,
        readonly=True,
        copy=False,
        help='External call identifier received from the Bulutsantralim PBX webhook.'
        ' Used to correlate CALL_START and CALL_END events.',
    )

    def create_and_format(
            self,
            res_id=None,
            res_model=None,
            **kwargs,
      ):
        """
        Block creation of an outgoing call if the destination has rejected
        IYS ARAMA consent. Only outgoing calls are blocked; incoming calls
        are not blocked here.
        """

        direction = kwargs.get(
            'direction',
            'outgoing',
         )

        if direction == 'outgoing':
            phone_number = kwargs.get(
                'phone_number',
                '',
            )

            normalized = _normalize_phone(phone_number) or phone_number

            Consent = self.env['iys.consent']

            if Consent._is_blocked(
                    normalized,
                    'ARAMA',
            ):
                raise UserError(
                    self.env._(
                        'IYS ARAMA consent is rejected for %s. Call blocked.',
                        phone_number,
                    )
                )

        return super().create_and_format(
            res_id=res_id,
            res_model=res_model,
            **kwargs,
        )
