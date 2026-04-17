import datetime
import logging
import re

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ARAS_STATUS_MAP = {
    '1': 'at_departure',
    '2': 'in_transit',
    '3': 'at_delivery_branch',
    '4': 'out_for_delivery',
    '5': 'partial_delivery',
    '6': 'delivered',
    '7': 'redirected',
}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('aras', 'Aras Kargo')],
        ondelete={'aras': 'set default'},
    )

    aras_username = fields.Char(string="Username")
    aras_password = fields.Char(string="Password")
    aras_customer_code = fields.Char(string="Customer Code")
    aras_sender_address_id = fields.Char(
        string="Sender Address ID",
        help="Sender address ID registered in Aras Kargo. "
             "Enter the relevant ID if you have multiple sender addresses.",
    )

    def _get_aras_credentials(self):
        self.ensure_one()
        return self.sudo().read([
            'aras_username',
            'aras_password',
            'aras_customer_code',
            'aras_sender_address_id',
        ])[0]

    def _get_aras_client(self):
        from .aras_shipping_client import ArasShippingClient
        secret_values = self._get_aras_credentials()
        env = 'prod' if self.prod_environment else 'test'
        return ArasShippingClient(
            username=secret_values.get('aras_username') or '',
            password=secret_values.get('aras_password') or '',
            customer_code=secret_values.get('aras_customer_code') or '',
            environment=env,
        )

    @staticmethod
    def _sanitize_phone(raw_phone):
        if not raw_phone:
            return ''
        digits = re.sub(r'\D', '', raw_phone)
        if digits.startswith('90') and len(digits) > 10:
            digits = digits[2:]
        elif digits.startswith('0') and len(digits) == 11:
            digits = digits[1:]
        return digits[:10]

    def _generate_aras_integration_code(self, picking):
        now = datetime.datetime.now()
        time_part = now.strftime("%y%m%d%H%M")
        picking_part = str(picking.id).zfill(6)
        return "%s%s" % (time_part, picking_part)

    @staticmethod
    def _extract_tracking_number(result):
        if not result:
            return ''

        candidate_fields = (
            'TrackingNumber',
            'TRACKINGNUMBER',
            'KARGO TAKİP NO',
            'KARGO_TAKIP_NO',
            'CargoKey',
            'CARGOKEY',
            'WaybillNo',
            'WAYBILLNO',
            'ShipmentNo',
            'SHIPMENTNO',
        )

        for field_name in candidate_fields:
            if isinstance(result, dict):
                value = result.get(field_name, '')
            else:
                value = getattr(result, field_name, '')

            value = str(value or '').strip()
            if value and value.lower() != 'none':
                return value

        return ''

    def _generate_barcode_numbers(self, integration_code, piece_count):
        return [
            "%s%s" % (integration_code, str(i).zfill(2))
            for i in range(1, piece_count + 1)
        ]

    def _get_aras_warning_message(self, integration_code, record_confirmed=False):
        self.ensure_one()
        if record_confirmed:
            return _(
                "Aras record found. Tracking reference will be available "
                "after the barcode is scanned. Integration Code: %s"
            ) % integration_code
        return _(
            "Aras record created. Tracking reference will be available "
            "after the barcode is scanned. Integration Code: %s"
        ) % integration_code

    def _get_piece_count(self, picking):
        packages = picking.move_line_ids.mapped('result_package_id')
        return len(packages) if packages else 1

    def _prepare_piece_details(self, picking, integration_code):
        piece_count = self._get_piece_count(picking)
        barcodes = self._generate_barcode_numbers(integration_code, piece_count)
        packages = picking.move_line_ids.mapped('result_package_id')

        details = []
        for idx, barcode in enumerate(barcodes):
            piece = {
                'BarcodeNumber': barcode,
                'VolumetricWeight': '1',
                'Weight': '1',
                'ProductNumber': '',
                'Description': '',
            }
            if packages and idx < len(packages):
                pkg = packages[idx]
                if pkg.shipping_weight:
                    piece['Weight'] = str(pkg.shipping_weight)
                    piece['VolumetricWeight'] = str(pkg.shipping_weight)
            elif picking.weight:
                w = str(round(picking.weight / piece_count, 2))
                piece['Weight'] = w
                piece['VolumetricWeight'] = w
            details.append(piece)
        return details, barcodes

    def _prepare_aras_order_data(self, picking, integration_code):
        partner = picking.partner_id
        secret_values = self._get_aras_credentials()
        piece_details, barcodes = self._prepare_piece_details(picking, integration_code)
        piece_count = len(piece_details)

        address = ' '.join(filter(None, [partner.street, partner.street2]))[:250]
        phone1 = self._sanitize_phone(partner.mobile or partner.phone or '')
        phone2 = self._sanitize_phone(
            partner.phone if (partner.mobile and partner.phone) else ''
        )

        waybill = picking.name or ''
        waybill = re.sub(r'[^A-Za-z0-9]', '', waybill)[:16]

        order_data = {
            'UserName': secret_values.get('aras_username') or '',
            'Password': secret_values.get('aras_password') or '',
            'TradingWaybillNumber': waybill,
            'InvoiceNumber': (picking.origin or '')[:20],
            'IntegrationCode': integration_code,
            'ReceiverName': (partner.name or '')[:100],
            'ReceiverAddress': address or 'No address provided',
            'ReceiverPhone1': phone1,
            'ReceiverPhone2': phone2,
            'ReceiverPhone3': '',
            'ReceiverCityName': (partner.state_id.name if partner.state_id else '')[:40],
            'ReceiverTownName': (partner.city or '')[:16],
            'ReceiverDistrictName': '',
            'ReceiverQuarterName': '',
            'ReceiverAvenueName': '',
            'ReceiverStreetName': '',
            'VolumetricWeight': str(picking.weight or 1.0),
            'Weight': str(picking.weight or 1.0),
            'PieceCount': piece_count,
            'PayorTypeCode': '1',
            'IsWorldWide': '0',
            'IsCod': '0',
            'CodAmount': '0',
            'CodCollectionType': '0',
            'CodBillingType': '0',
            'SpecialField1': '',
            'SpecialField2': '',
            'SpecialField3': '',
            'Description': '',
        }

        if piece_details:
            order_data['PieceDetails'] = piece_details

        sender_address_id = secret_values.get('aras_sender_address_id')
        if sender_address_id:
            order_data['SenderAccountAddressId'] = sender_address_id

        if picking.aras_is_cod and picking.aras_cod_amount:
            order_data.update({
                'IsCod': '1',
                'CodAmount': str(picking.aras_cod_amount),
                'CodCollectionType': picking.aras_cod_type or '0',
                'CodBillingType': '0',
            })

        return order_data, barcodes

    def aras_rate_shipment(self, order):
        self.ensure_one()
        price = self.product_id.list_price if self.product_id else 0.0
        return {
            'success': True,
            'price': price,
            'error_message': False,
            'warning_message': False,
        }

    def aras_send_shipping(self, pickings):
        res = []
        for picking in pickings:
            if picking.aras_integration_code and picking.aras_delivery_state != 'canceled':
                warning_message = (
                    picking.aras_last_sync_warning
                    or self._get_aras_warning_message(
                        picking.aras_integration_code,
                        record_confirmed=bool(picking.carrier_tracking_ref),
                    )
                )
                res.append({
                    'exact_price': self.product_id.list_price if self.product_id else 0.0,
                    'tracking_number': False,
                    'warning_message': warning_message,
                })
                continue

            client = self._get_aras_client()
            integration_code = self._generate_aras_integration_code(picking)
            order_data, barcodes = self._prepare_aras_order_data(picking, integration_code)

            client.create_order(order_data)
            warning_message = self._get_aras_warning_message(
                integration_code,
                record_confirmed=False,
            )

            picking.write({
                'aras_integration_code': integration_code,
                'aras_barcode_numbers': ','.join(barcodes),
                'aras_sync_pending': True,
                'aras_delivery_state': False,
                'aras_last_sync_warning': warning_message,
                'carrier_tracking_ref': False,
            })

            if warning_message:
                picking.message_post(body=warning_message, message_type='notification')

            res.append({
                'exact_price': self.product_id.list_price if self.product_id else 0.0,
                'tracking_number': False,
                'warning_message': warning_message,
            })
        return res

    def aras_get_tracking_link(self, picking):
        self.ensure_one()
        if picking.carrier_tracking_ref:
            return (
                "https://www.araskargo.com.tr/kargo-takip"
                "?kargo_takip_no=%s" % picking.carrier_tracking_ref
            )
        return False

    def _update_picking_from_query(self, picking, data):
        vals = {}

        tracking = self._extract_tracking_number(data)
        if tracking and tracking != 'None' and picking.carrier_tracking_ref != tracking:
            vals['carrier_tracking_ref'] = tracking
            vals['aras_last_sync_warning'] = False
        elif not picking.carrier_tracking_ref:
            vals['aras_last_sync_warning'] = self._get_aras_warning_message(
                picking.aras_integration_code,
                record_confirmed=True,
            )

        status_code = str(data.get('DURUM KODU', data.get('DURUM_KODU', ''))).strip()
        new_state = ARAS_STATUS_MAP.get(status_code)
        if new_state and picking.aras_delivery_state != new_state:
            vals['aras_delivery_state'] = new_state

        if new_state == 'delivered':
            vals['aras_sync_pending'] = False

        tip_code = str(data.get('TİP KODU', data.get('TIP_KODU', ''))).strip()
        if tip_code == '3':
            vals['aras_delivery_state'] = 'returned'
            vals['aras_sync_pending'] = False

        deliver_person = str(data.get('TESLİM ALAN', data.get('TESLIM_ALAN', ''))).strip()
        if deliver_person and deliver_person != 'None':
            vals['aras_delivery_person'] = deliver_person

        deliver_date = str(data.get('TESLİM TARİHİ', data.get('TESLIM_TARIHI', ''))).strip()
        if deliver_date and deliver_date != 'None':
            vals['aras_delivery_date'] = deliver_date

        deliver_time = str(data.get('TESLİM SAATİ', data.get('TESLIM_SAATI', ''))).strip()
        if deliver_time and deliver_time != 'None':
            current = vals.get('aras_delivery_date', picking.aras_delivery_date or '')
            if current:
                vals['aras_delivery_date'] = "%s %s" % (current, deliver_time)

        return_reason = str(
            data.get('İADE SEBEBİ', data.get('IADE_SEBEBI',
            data.get('DEVİR KODU', data.get('DEVIR_KODU', ''))))
        ).strip()
        if return_reason and return_reason != 'None':
            vals['aras_return_reason'] = return_reason

        if vals:
            picking.write(vals)

    @staticmethod
    def _get_field(result, field, default=''):
        if isinstance(result, dict):
            return result.get(field, default)
        return getattr(result, field, default)

    def _update_picking_from_order_service(self, picking, result):
        vals = {}
        tracking_no = self._extract_tracking_number(result)
        if tracking_no and tracking_no not in ('None', 'none'):
            if picking.carrier_tracking_ref != tracking_no:
                vals['carrier_tracking_ref'] = tracking_no
            vals['aras_last_sync_warning'] = False
        elif not picking.carrier_tracking_ref:
            vals['aras_last_sync_warning'] = self._get_aras_warning_message(
                picking.aras_integration_code,
                record_confirmed=True,
            )

        is_delivered = str(self._get_field(result, 'IsDelivered', 'false')).lower()
        if is_delivered in ('true', '1'):
            vals['aras_delivery_state'] = 'delivered'
            vals['aras_sync_pending'] = False
        elif tracking_no and picking.aras_delivery_state == 'at_departure':
            vals['aras_delivery_state'] = 'in_transit'

        if vals:
            picking.write(vals)

    def aras_tracking_state_update(self, picking):
        self.ensure_one()
        if not picking.aras_integration_code:
            return False

        client = self._get_aras_client()

        if self.aras_customer_code:
            data = client.query_shipment_detail(picking.aras_integration_code)
            if data:
                self._update_picking_from_query(picking, data)
                _logger.info(
                    "Aras query sync for %s: tracking=%s state=%s",
                    picking.name,
                    picking.carrier_tracking_ref or '-',
                    picking.aras_delivery_state or '-',
                )
                return True

        result = client.get_order_status(picking.aras_integration_code)
        if result:
            self._update_picking_from_order_service(picking, result)
            _logger.info(
                "Aras order sync for %s: tracking=%s state=%s",
                picking.name,
                picking.carrier_tracking_ref or '-',
                picking.aras_delivery_state or '-',
            )
            return True

        warning_message = self._get_aras_warning_message(
            picking.aras_integration_code,
            record_confirmed=False,
        )
        if picking.aras_last_sync_warning != warning_message:
            picking.write({'aras_last_sync_warning': warning_message})
        _logger.warning(
            "Aras sync returned no data for %s (integration=%s)",
            picking.name,
            picking.aras_integration_code,
        )
        return False

    def aras_cancel_shipment(self, picking):
        self.ensure_one()
        if not picking.aras_integration_code:
            raise UserError(_("This shipment does not have an Aras integration code."))

        client = self._get_aras_client()
        result = client.cancel_order(picking.aras_integration_code)

        if not result.get('success'):
            raise UserError(
                _("Aras Kargo cancellation failed: %s") % result.get('message', 'Unknown error')
            )
        return True
