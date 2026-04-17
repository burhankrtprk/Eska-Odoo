# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models
from odoo.addons.sms.tools.sms_api import SmsApiBase
from odoo.addons.sms.tools.sms_api import SmsApi

_logger = logging.getLogger(__name__)

_VERIMOR_SMS_ENDPOINT = 'https://sms.verimor.com.tr/v2/send.json'


class VerimorSmsApi(SmsApiBase):
    """
    Pure Verimor SMS transport — sends messages via v2/send.json.
    No IYS logic here; IYS blocking is in iys_sms/models/sms_sms.py.
    """

    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        'server_error': 'sms_server',
        'wrong_number_format': 'sms_number_format',
    }

    def _get_credentials(self):
        account = self.env['iap.account'].search(
            [('provider', '=', 'sms_verimor')], limit=1
        )

        if not account:
            return {}
        return {
            'username': account.sms_username or '',
            'password': account.sms_password or '',
            'source_addr': account.sms_source_addr or '',
        }

    def _send_sms_batch(self, messages, delivery_reports_url=False):

        creds = self._get_credentials()

        if not creds.get('username') or not creds.get('password'):

            return [
                {'uuid': rec['uuid'],
                 'state': 'server_error',
                 'failure_reason': 'credentials_missing',
             }

                for msg in messages for rec in msg['numbers']
            ]

        results = []

        for message in messages:
            content = message.get('content', '')
            numbers = message.get('numbers', [])

            verimor_messages = [
                {'msg': content,
                 'dest': rec['number'],
                 'id': rec['uuid'],
             }
                for rec in numbers
            ]

            payload = {
                'username': creds['username'],
                'password': creds['password'],
                'source_addr': creds['source_addr'],
                'is_commercial': True,
                'iys_recipient_type': 'BIREYSEL',
                'messages': verimor_messages,
            }

            try:
                resp = requests.post(_VERIMOR_SMS_ENDPOINT,
                                     json=payload,
                                     timeout=20,
                 )
            except requests.RequestException as exc:
                results.extend([
                    {'uuid': rec['uuid'],
                     'state': 'server_error',
                     'failure_reason': str(exc),
                 }
                    for rec in numbers
                ])
                continue

            if resp.status_code == 200:
                results.extend([{'uuid': rec['uuid'],
                                 'state': 'success'} for rec in numbers])

            else:
                results.extend([
                    {'uuid': rec['uuid'],
                     'state': 'server_error',
                     'failure_reason': resp.text.strip(),
             }
                    for rec in numbers
                ])

        return results

    def _get_sms_api_error_messages(self):

        error_dict = super()._get_sms_api_error_messages()
        error_dict.update({
            'server_error': 'An error occurred on the Verimor SMS gateway.',
            'wrong_number_format': 'The phone number is not in a valid format for Verimor.',
            'credentials_missing': 'Verimor SMS credentials are not configured.',
        })

        return error_dict


class ResCompany(models.Model):

    _inherit = 'res.company'

    def _get_sms_api_class(self):

        self.ensure_one()

        account = self.env['iap.account'].search(
            [('provider', '=', 'sms_verimor')],
            limit=1,
        )

        if account and account.sms_username:
            return VerimorSmsApi

        return SmsApi
