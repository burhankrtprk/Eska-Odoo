# -*- coding: utf-8 -*-
import datetime
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bulutsantralim (bulutsantralim.com) webhook event types
#
# Bulutsantralim, PBX olaylarını HTTP POST ile gönderir.
# Payload örneği (JSON):
#
#   CALL_START:
#   {
#       "event": "CALL_START",
#       "caller": "905551234567",
#       "callee": "905557654321",
#       "direction": "inbound",       # "inbound" | "outbound"
#       "call_id": "abc123xyz",
#       "timestamp": "2025-01-13T15:00:00Z"
#   }
#
#   CALL_END:
#   {
#       "event": "CALL_END",
#       "call_id": "abc123xyz",
#       "duration": 120,              # saniye
#       "hangup_cause": "NORMAL_CLEARING",
#       "timestamp": "2025-01-13T15:02:00Z"
#   }
#
#   CALL_MISSED:
#   {
#       "event": "CALL_MISSED",
#       "caller": "905551234567",
#       "callee_extension": "101",
#       "call_id": "abc123xyz",
#       "timestamp": "2025-01-13T15:00:05Z"
#   }
#
# ---------------------------------------------------------------------------

# Bulutsantralim → Odoo voip.call state eşlemesi
_HANGUP_STATE_MAP = {
    'NORMAL_CLEARING': 'terminated',
    'NO_ANSWER': 'missed',
    'USER_BUSY': 'rejected',
    'ORIGINATOR_CANCEL': 'aborted',
}


class BulutsantralimWebhook(http.Controller):
    """
    Bulutsantralim PBX'inden gelen gerçek zamanlı arama olaylarını işler.

    Endpoint: POST /iys_voip/webhook

    PBX tarafında bu URL yapılandırılmalıdır:
        https://<odoo-domain>/iys_voip/webhook

    Güvenlik:
        - Bulutsantralim panelinden ayarlanan bir shared secret, her istekte
          X-Webhook-Secret başlığı ile gönderilir.
        - Odoo tarafında bu değer ir.config_parameter'a
          'iys_voip.webhook_secret' anahtarıyla kaydedilir.
        - Secret eşleşmezse 403 döner.
        - Secret tanımlı değilse uyarı loglanır ve istek işlenir
          (geliştirme ortamları için tolerans).
    """

    @http.route(
        '/iys_voip/webhook',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def bulutsantralim_webhook(self, **_kwargs):
        """Ana webhook alıcısı."""
        # ---- 1. Payload parse ----
        try:
            raw = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            _logger.warning('iys_voip webhook: invalid JSON – %s', exc)
            return request.make_json_response({'error': 'invalid_json'}, status=400)

        _logger.debug('iys_voip webhook payload: %s', payload)

        # ---- 2. Secret doğrulama ----
        if not self._verify_secret(request):
            return request.make_json_response({'error': 'forbidden'}, status=403)

        # ---- 3. Event dispatch ----
        event = (payload.get('event') or '').upper()
        handler = {
            'CALL_START': self._on_call_start,
            'CALL_END': self._on_call_end,
            'CALL_MISSED': self._on_call_missed,
        }.get(event)

        if handler is None:
            _logger.info('iys_voip webhook: unknown event %r – ignored.', event)
            return request.make_json_response({'status': 'ignored', 'event': event})

        try:
            handler(payload)
        except Exception as exc:  # noqa: BLE001
            _logger.exception('iys_voip webhook: error handling event %r – %s', event, exc)
            return request.make_json_response({'error': 'internal_error'}, status=500)

        return request.make_json_response({'status': 'ok', 'event': event})

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_call_start(self, payload):
        """
        Yeni bir arama başladığında çağrılır.

        - Odoo'da 'calling' state ile yeni bir voip.call kaydı oluşturur.
        - Gelen aramaysa sorumlu kullanıcıya bus notification gönderir.
        """
        call_id_ext = payload.get('call_id', '')
        phone_raw = payload.get('caller') or payload.get('callee') or ''
        direction_raw = (payload.get('direction') or 'inbound').lower()

        # Bulutsantralim 'inbound'/'outbound' → Odoo 'incoming'/'outgoing'
        direction = 'incoming' if direction_raw == 'inbound' else 'outgoing'

        # Giden aramalar create_and_format() ile zaten oluşturulur (voip.call model),
        # webhook'tan tekrar oluşturmaya gerek yok.
        if direction == 'outgoing':
            _logger.debug(
                'iys_voip webhook: CALL_START outgoing (ext_id=%s) – skipped (already created by softphone).',
                call_id_ext,
            )
            return

        env = request.env(su=True)
        phone = self._normalize(phone_raw)

        # Eğer partner bulunursa kayıt ona bağlanır
        partner = env['res.partner'].search(
            [('phone_mobile_search', '=', phone)], limit=1
        )

        voip_call = env['voip.call'].create({
            'phone_number': phone or phone_raw,
            'direction': direction,
            'state': 'calling',
            'partner_id': partner.id if partner else False,
            'bulutsantralim_call_id': call_id_ext,
        })

        # Sorumlu kullanıcıyı bul (dahili numara -> res.users)
        extension = payload.get('callee_extension') or payload.get('callee') or ''
        responsible_user = self._find_user_by_extension(env, extension)

        # Bus notification – Odoo VoIP JS bu mesajı dinler
        if responsible_user:
            env['bus.bus']._sendone(
                responsible_user.partner_id,
                'voip.call/incoming',
                {
                    'id': voip_call.id,
                    'phoneNumber': phone or phone_raw,
                    'partner': partner._format_contacts()[0] if partner else False,
                },
            )
            _logger.info(
                'iys_voip webhook: CALL_START – incoming from %s, notified user %s (voip.call id=%d).',
                phone, responsible_user.login, voip_call.id,
            )
        else:
            _logger.info(
                'iys_voip webhook: CALL_START – incoming from %s, no responsible user found (ext=%r).',
                phone, extension,
            )

    def _on_call_end(self, payload):
        """
        Arama sona erdiğinde çağrılır.

        - Daha önce oluşturulan voip.call kaydını günceller.
        - hangup_cause değerine göre state ('terminated', 'missed', vb.) atanır.
        """
        call_id_ext = payload.get('call_id', '')
        hangup_cause = (payload.get('hangup_cause') or 'NORMAL_CLEARING').upper()
        duration = payload.get('duration')  # saniye cinsinden

        env = request.env(su=True)
        voip_call = self._find_voip_call(env, call_id_ext)
        if not voip_call:
            _logger.warning(
                'iys_voip webhook: CALL_END – no voip.call found for ext_id=%r.', call_id_ext
            )
            return

        new_state = _HANGUP_STATE_MAP.get(hangup_cause, 'terminated')

        write_vals = {'state': new_state}
        if duration is not None and new_state == 'terminated':
            # start_date'i retroaktif hesapla (end_date - duration)
            now = fields.Datetime.now()
            write_vals['end_date'] = now
            write_vals['start_date'] = now - datetime.timedelta(seconds=int(duration))

        voip_call.write(write_vals)

        _logger.info(
            'iys_voip webhook: CALL_END – voip.call id=%d state=%s (hangup_cause=%s, duration=%ss).',
            voip_call.id, new_state, hangup_cause, duration,
        )

    def _on_call_missed(self, payload):
        """
        Cevapsız arama olayı için kısayol.

        Bulutsantralim bazen CALL_MISSED ayrı bir event olarak da gönderir.
        CALL_END + hangup_cause=NO_ANSWER ile aynı davranışı üretir.
        """
        payload_normalized = dict(payload, hangup_cause='NO_ANSWER')
        # call_id varsa mevcut kaydı güncelle; yoksa yeni kayıt oluştur
        call_id_ext = payload.get('call_id', '')
        env = request.env(su=True)
        existing = self._find_voip_call(env, call_id_ext)

        if existing:
            self._on_call_end(payload_normalized)
        else:
            # Doğrudan missed state ile kayıt aç
            phone_raw = payload.get('caller', '')
            phone = self._normalize(phone_raw)
            partner = env['res.partner'].search(
                [('phone_mobile_search', '=', phone)], limit=1
            )
            env['voip.call'].create({
                'phone_number': phone or phone_raw,
                'direction': 'incoming',
                'state': 'missed',
                'partner_id': partner.id if partner else False,
            })
            _logger.info(
                'iys_voip webhook: CALL_MISSED – created missed call record for %s.', phone
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_secret(req):
        """
        İstekteki X-Webhook-Secret başlığını ir.config_parameter'daki değerle karşılaştırır.

        - Secret tanımlıysa: birebir eşleşme zorunlu, aksi hâlde 403.
        - Secret tanımlı değilse:
            - Odoo --dev / debug modunda: uyarı logla, isteği kabul et (geliştirme kolaylığı).
            - Production modunda: 403 döndür.

        Odoo'da debug modu: tools.config['dev_mode'] listesi boş değilse aktiftir.

        :return: True → isteği kabul et | False → reddet (403)
        """
        env = req.env(su=True)
        expected = env['ir.config_parameter'].sudo().get_param('iys_voip.webhook_secret')

        if not expected:
            from odoo.tools import config as odoo_config
            dev_mode = bool(odoo_config.get('dev_mode'))
            if dev_mode:
                _logger.warning(
                    'iys_voip webhook: iys_voip.webhook_secret not set – '
                    'accepting request in dev mode. '
                    'Set this param before deploying to production.'
                )
                return True
            _logger.error(
                'iys_voip webhook: iys_voip.webhook_secret not configured – '
                'request rejected. '
                'Go to Settings → Technical → System Parameters and add '
                '"iys_voip.webhook_secret" with the secret defined in Bulutsantralim panel.'
            )
            return False

        received = req.httprequest.headers.get('X-Webhook-Secret', '')
        if received != expected:
            _logger.warning(
                'iys_voip webhook: secret mismatch – request rejected '
                '(received prefix=%r).', received[:8] + '…' if received else '<empty>'
            )
            return False

        return True

    @staticmethod
    def _normalize(phone):
        """
        Ham telefon numarasını Verimor uyumlu E.164 formatına çevirir
        (örn. '05551234567' → '905551234567').

        Türkiye dışı numaralar için None döner.
        """
        from odoo.addons.iys.models.res_partner import _normalize_phone
        return _normalize_phone(phone) or phone or ''

    @staticmethod
    def _find_voip_call(env, call_id_ext):
        """
        Bulutsantralim call_id string'ini kullanarak daha önce oluşturulan
        voip.call kaydını bulur.

        voip.call.bulutsantralim_call_id alanı üzerinden arama yapılır.
        """
        if not call_id_ext:
            return None
        return env['voip.call'].search(
            [('bulutsantralim_call_id', '=', call_id_ext)], limit=1
        ) or None

    @staticmethod
    def _find_user_by_extension(env, extension):
        """
        Bulutsantralim dahili numarasını Odoo res.users kaydına eşler.

        res.users'a 'voip_extension' alanı eklendiği varsayılır.
        (voip modülüne bak: res_users.py → sip_login / voip_login)
        """
        if not extension:
            return None
        # Odoo native VoIP: voip_provider_id + sip_login
        user = env['res.users'].search(
            [('sip_login', '=', extension)], limit=1
        )
        return user or None
