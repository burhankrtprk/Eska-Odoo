# -*- coding: utf-8 -*-
import logging
import requests
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from dateutil import parser as dateparser

_logger = logging.getLogger(__name__)

CONSENT_TYPES = ['MESAJ', 'ARAMA', 'EPOSTA']


_IYS_PUSH_ENDPOINT = 'https://sms.verimor.com.tr/v2/iys_consents.json'
_IYS_PULL_ENDPOINT = 'https://sms.verimor.com.tr/v2/iys_status.json'


class IysConsent(models.Model):
    """
    Central IYS consent store.

    One record per pair:
      - status='RET'  + active=False  → blacklisted
      - status='ONAY' + active=True   → explicitly allowed
      - no record                     → pending

    Two-Way Sync:
      - Odoo → IYS: triggered by res.partner write()
      - IYS → Odoo: cron job calls _pull_from_iys()
    """
    _name = 'iys.consent'
    _description = 'IYS Consent'
    _order = 'write_date desc, id desc'
    _rec_name = 'recipient'

    recipient = fields.Char(
        required=True,
        index=True,
        help='E.164 phone number (905XXXXXXXXX) or e-mail address',
    )

    consent_type = fields.Selection(
        selection=[
            ('MESAJ', 'SMS'),
            ('ARAMA', 'Voice Call'),
            ('EPOSTA', 'E-Mail'),
        ],
        required=True,
        index=True,
    )

 #onay durumu bekleniyor yazılacak
    status = fields.Selection(
        selection=[
            ('ONAY', 'Approved'),
            ('RET', 'Rejected'),
        ],
        required=True,
    )

    active = fields.Boolean(
        default=True,
    )

    source = fields.Char(
        default='HS_WEB',
        help='IYS source code (HS_WEB, HS_CAGRI_MERKEZI, etc.)',
    )
#buradai türkçe alan adları kaldırılacak
    recipient_type = fields.Selection(
        selection=[('BIREYSEL', 'Individual'), ('TACIR', 'Merchant')],
        default='BIREYSEL',
    )

    consent_date = fields.Datetime(
        default=fields.Datetime.now,
    )

    _sql_constraints = [
        (
            'unique_recipient_type',
            'UNIQUE(recipient, consent_type)',
            'A consent record already exists for this recipient and consent type.',
        ),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def _add(self, recipient, consent_type, status, source='HS_WEB',
             recipient_type='BIREYSEL', consent_date=None):
        """
        Add or update a consent record.

        :param recipient: E.164 phone or e-mail
        :param consent_type: 'MESAJ' | 'ARAMA' | 'EPOSTA'
        :param status: 'ONAY' | 'RET'
        :param source: IYS source code
        :param recipient_type: 'BIREYSEL' | 'TACIR'
        :param consent_date: datetime or None (defaults to now)
        :return: iys.consent record
        """

        if consent_type not in CONSENT_TYPES:
            raise ValidationError(
                self.env._(
                    "Invalid consent_type '%(ctype)s'. Must be one of %(types)s.",
                    {
                        'ctype': consent_type,
                        'types': CONSENT_TYPES,
                    }
                )
            )

        #türkçe isimlendirmeler değişecek
        if status not in ('ONAY', 'RET'):
            raise ValidationError(
                self.env._("Invalid status '%s'. Must be 'ONAY' or 'RET'.", status)
            )

        recipient = (recipient or '').strip().lower() \
            if '@' in (recipient or '') \
            else (recipient or '').strip()

        existing = self.search([
            ('recipient', '=', recipient),
            ('consent_type', '=', consent_type),
        ], limit=1)
#türkçe değişcek
        vals = {
            'status': status,
            'active': status == 'ONAY',
            'source': source,
            'recipient_type': recipient_type,
            'consent_date': consent_date or fields.Datetime.now(),
        }

        if existing:
            existing.sudo().write(vals)
            return existing
        else:
            vals.update({
                'recipient': recipient,
                'consent_type': consent_type,
            })
            return self.sudo().create(vals)

    @api.model
    def _remove(self, recipient, consent_type):
        """
        Remove (unlink) a consent record.

        :param recipient: E.164 phone or e-mail
        :param consent_type: 'MESAJ' | 'ARAMA' | 'EPOSTA'
        """

        recipient = (recipient or '').strip().lower() \
            if '@' in (recipient or '') \
            else (recipient or '').strip()

        record = self.search([
            ('recipient', '=', recipient),
            ('consent_type', '=', consent_type),
        ], limit=1)

        if record:
            record.sudo().unlink()

    @api.model
    def _lookup(self, recipient, consent_type):
        """
        Return the consent status for a given recipient and type.

        :return: 'ONAY' | 'RET' | 'pending'
        #türkçe değişcek
        """

        recipient = (recipient or '').strip().lower() \
            if '@' in (recipient or '') \
            else (recipient or '').strip()

        record = self.with_context(active_test=False).search([
            ('recipient', '=', recipient),
            ('consent_type', '=', consent_type),
        ], limit=1)

        if not record:
            return 'pending'
        return record.status

    @api.model
    def _is_blocked(self, recipient, consent_type):
        """Return True if the recipient has explicitly rejected this consent type."""
        # türkçe değişcek

        return self._lookup(recipient, consent_type) == 'RET'

    # ------------------------------------------------------------------
    # Two-Way Sync
    # ------------------------------------------------------------------

    @api.model
    def _pull_from_iys(self):
        """
        Cron job entry point

        Strategy:
          1. Collect all (recipient, consent_type) pairs known in iys.consent.
          2. Send a batch status query to Verimor.
          3. For each returned record, compare with local and update if changed.
          4. Propagate changes to matching res.partner records.
          5. Update iys_last_pull_date on the iap.account credential record.
        """

        account = self.env['iap.account'].search(
            [('provider', '=', 'iys_verimor')], limit=1
        )

        if not account or not account.iys_username or not account.iys_password:
            _logger.warning('iys: Pull skipped – IYS credentials not configured.')
            return

        # Collect all known (recipient, type) pairs
        local_records = self.with_context(active_test=False).search([])  # pylint: disable=no-search-all

        if not local_records:
            _logger.info('iys: Pull skipped – no local consent records found.')
            return

        # Build query payload: ask Verimor for the current status of all known recipients
        query_items = [
            {'recipient': rec.recipient, 'type': rec.consent_type}
            for rec in local_records
        ]

        payload = {
            'username': account.iys_username,
            'password': account.iys_password,
            'consents': query_items,
        }

        try:
            resp = requests.post(_IYS_PULL_ENDPOINT, json=payload, timeout=30)
        except requests.RequestException as exc:
            _logger.exception('iys: Pull request failed: %s', exc)
            return

        if resp.status_code != 200:
            _logger.error('iys: Pull failed – HTTP %s: %s', resp.status_code, resp.text)
            return

        try:
            remote_data = resp.json()  # list of {recipient, type, status, consent_date}
        except ValueError:
            _logger.error('iys: Pull returned invalid JSON: %s', resp.text[:200])
            return

        # Index local records for fast lookup: (recipient, consent_type) → record
        local_index = {(r.recipient, r.consent_type): r for r in local_records}

        changed_records = self.env['iys.consent']

        for item in remote_data:
            recipient = item.get('recipient', '').strip()
            c_type = item.get('type', '').strip()
            remote_status = item.get('status', '').strip()  # 'ONAY' or 'RET'
            remote_date_str = item.get('consent_date')
            # türkçe değişcek
            if not recipient or c_type not in CONSENT_TYPES or remote_status not in ('ONAY', 'RET'):
                continue

            # Normalise recipient
            if '@' in recipient:
                recipient = recipient.lower()

            key = (recipient, c_type)
            local = local_index.get(key)

            if local and local.status == remote_status:
                # No change
                continue

            # Status changed – update local record without triggering Odoo→IYS push
            # (skip _sync and _push by using a special context flag)
            consent_date = None
            if remote_date_str:
                try:
                    consent_date = dateparser.parse(remote_date_str)
                except (ValueError, ImportError):
                    _logger.warning("iys: Invalid remote_date_str '%s'", remote_date_str)

            updated = self._add(
                recipient=recipient,
                consent_type=c_type,
                status=remote_status,
                source='IYS_PULL',
                consent_date=consent_date,
            )

            changed_records |= updated

            _logger.info(
                'iys: Pull – updated %s [%s]: %s → %s',
                recipient, c_type,
                local.status if local else 'pending',
                remote_status,
            )

        # Propagate changes to matching res.partner records
        if changed_records:
            self._propagate_to_partners(changed_records)

        # Update last pull timestamp
        account.sudo().write({'iys_last_pull_date': fields.Datetime.now()})

        _logger.info('iys: Pull complete – %d record(s) updated.', len(changed_records))

    @api.model
    def _propagate_to_partners(self, changed_consents):
        """
        Find res.partner records matching the changed consent recipients and
        call _apply_iys_pull() on them so each channel module can update its
        own consent field.

        :param changed_consents: iys.consent recordset
        """

        Partner = self.env['res.partner']

        for consent in changed_consents:
            recipient = consent.recipient
            c_type = consent.consent_type
            status = consent.status

            if '@' in recipient:
                # E-mail based consent (EPOSTA)
                partners = Partner.search([('email', '=ilike', recipient)])
            else:
                # Phone-based consent (MESAJ / ARAMA)
                partners = Partner.search([('verimor_mobile', '=', recipient)])

            if not partners:
                _logger.debug(
                    'iys: No partner found for recipient %s (%s) – skipping propagation.',
                    recipient, c_type,
                )
                continue

            # Use context flag to prevent write() from re-triggering push to IYS
            partners.with_context(iys_skip_push=True)._apply_iys_pull(c_type, status)
