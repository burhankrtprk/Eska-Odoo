# -*- coding: utf-8 -*-
import json
import logging
import requests
from datetime import timedelta
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_IYS_PUSH_ENDPOINT = 'https://sms.verimor.com.tr/v2/iys_consents.json'

MAX_RETRIES = 3
BATCH_SIZE = 200   # max items processed per cron run
REQUEST_TIMEOUT = 15  # seconds


class IysPushQueue(models.Model):
    """
    Async queue for outgoing IYS consent push calls .

    Instead of blocking the user's browser while waiting for Verimor's API,
    consent changes are enqueued here and processed by a cron job every 5
    minutes. Failed attempts are retried with exponential backoff up to
    MAX_RETRIES times before being marked permanently failed.

    State machine:
        pending  →  done
        pending  →  pending
        pending  →  failed
    """

    _name = 'iys.push.queue'
    _description = 'IYS Push Queue'
    _order = 'create_date asc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        index=True,
        ondelete='cascade',
    )

    payload = fields.Text(
        string='Payload (JSON)',
        readonly=True,
        help='The JSON body that will be sent to the Verimor IYS API.',
    )

    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('done', 'Sent'),
            ('failed', 'Failed'),
        ],
        default='pending',
        index=True,
        readonly=True,
    )

    retry_count = fields.Integer(string='Retries', default=0, readonly=True)

    next_retry = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        readonly=True,
    )

    last_error = fields.Text(readonly=True)

    @api.model
    def _enqueue(self, partner, payload_dict):
        """
        Add a consent push request to the queue.

        Called by res.partner._push_iys_consents() instead of making
        the HTTP call directly. Returns immediately — no blocking.

        :param partner: res.partner record
        :param payload_dict: dict to be JSON-serialised and sent to IYS
        """

        self.sudo().create({
            'partner_id': partner.id,
            'payload': json.dumps(payload_dict, ensure_ascii=False),
            'state': 'pending',
            'retry_count': 0,
            'next_retry': fields.Datetime.now(),
        })

    @api.model
    def _process_queue(self):
        """
        Cron entry point

        Called every 5 minutes by the scheduled action.
        """

        account = self.env['iap.account'].search(
            [('provider', '=', 'iys_verimor')], limit=1
        )

        if (not account
                or not account.iys_username
                or not account.iys_password
        ):
            _logger.warning('iys.push.queue: skipped – IYS credentials not configured.')
            return

        pending = self.search([
            ('state', '=', 'pending'),
            ('next_retry', '<=', fields.Datetime.now()),
        ], limit=BATCH_SIZE)

        _logger.info(
            'iys.push.queue: processing %d item(s) (batch limit=%d).',
            len(pending), BATCH_SIZE,
        )

        for item in pending:
            try:
                with self.env.cr.savepoint():
                    item._send_one(account)

            except Exception as exc:  # noqa: BLE001
                _logger.exception(
                    'iys.push.queue: unexpected error processing item id=%d – %s',
                    item.id, exc,
                )

    def _send_one(self, account):
        """
        Attempt to send a single queued push request.

        Updates state, retry_count, and next_retry in place.
        """

        self.ensure_one()

        try:
            payload = json.loads(self.payload or '{}')

        except (ValueError, TypeError):
            self.sudo().write({
                'state': 'failed',
                'last_error': 'Invalid JSON payload in queue item.',
            })
            return

        # Inject fresh credentials
        payload['username'] = account.iys_username
        payload['password'] = account.iys_password

        try:
            resp = requests.post(
                _IYS_PUSH_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT
            )

            if resp.status_code == 200:
                self.sudo().write({'state': 'done', 'last_error': False})
                _logger.info(
                    'iys.push.queue: partner %s pushed successfully.',
                    self.partner_id.name,
                )
                return

            error = f'HTTP {resp.status_code}: {resp.text[:300]}'

        except requests.Timeout:
            error = f'Request timed out after {REQUEST_TIMEOUT}s.'

        except requests.RequestException as exc:
            error = str(exc)

        # Failed attempt — decide retry or permanent failure
        new_retry_count = self.retry_count + 1

        if new_retry_count >= MAX_RETRIES:
            self.sudo().write({
                'state': 'failed',
                'retry_count': new_retry_count,
                'last_error': error,
            })

            _logger.error(
                'iys.push.queue: partner %s permanently failed after %d retries: %s',
                self.partner_id.name, new_retry_count, error,
            )

        else:
            # Exponential backoff: 5 min, 10 min, 20 min …
            backoff_minutes = 5 * (2 ** new_retry_count)

            next_retry = fields.Datetime.now() + timedelta(minutes=backoff_minutes)

            self.sudo().write({
                'retry_count': new_retry_count,
                'next_retry': next_retry,
                'last_error': error,
            })

            _logger.warning(
                'iys.push.queue: partner %s failed (attempt %d/%d), retry in %d min: %s',
                self.partner_id.name, new_retry_count, MAX_RETRIES, backoff_minutes, error,
            )

    def action_retry_now(self):
        """Manual retry button."""
        self.sudo().write({
            'state': 'pending',
            'next_retry': fields.Datetime.now(),
            'last_error': False,
        })
