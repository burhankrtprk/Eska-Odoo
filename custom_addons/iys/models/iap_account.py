# -*- coding: utf-8 -*-
from odoo import fields, models


class IapAccount(models.Model):
    _inherit = 'iap.account'

    provider = fields.Selection(
        selection=[('iys_verimor', 'IYS Verimor')],
        ondelete={'iys_verimor': 'cascade'},
    )

    iys_username = fields.Char(
        string='IYS Username',
        help='Verimor account username used for IYS consent push (e.g. 908501234567)',
    )

    iys_password = fields.Char(
        string='IYS Password',
    )

    iys_source_addr = fields.Char(
        string='IYS Sender ID (Başlık)',
        help='Approved sender name registered on Verimor OIM panel',
    )

    iys_last_pull_date = fields.Datetime(
        string='Last IYS Pull',
        readonly=True,
        help='Timestamp of the last successful two-way sync from Verimor IYS API.',
    )


    def _get_service_from_provider(self):
        if self.provider == 'iys_verimor':
            return 'iys'
        return super()._get_service_from_provider()
