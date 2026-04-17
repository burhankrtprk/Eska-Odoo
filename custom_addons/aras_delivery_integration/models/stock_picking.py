import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    aras_integration_code = fields.Char(
        string="Aras Integration Code",
        copy=False,
        readonly=True,
    )
    aras_barcode_numbers = fields.Char(
        string="Piece Barcodes",
        copy=False,
        readonly=True,
        help="Comma-separated piece barcode numbers",
    )
    aras_sync_pending = fields.Boolean(
        string="Aras Sync Pending",
        default=False,
        copy=False,
    )
    carrier_total_deci = fields.Float(
        string="Actual Deci",
        copy=False,
    )
    carrier_shipping_total = fields.Float(
        string="Actual Shipping Cost",
        copy=False,
    )
    aras_delivery_state = fields.Selection(
        [
            ('at_departure', 'At Departure Branch'),
            ('in_transit', 'In Transit'),
            ('at_delivery_branch', 'At Delivery Branch'),
            ('out_for_delivery', 'Out for Delivery'),
            ('partial_delivery', 'Partial Delivery'),
            ('delivered', 'Delivered'),
            ('redirected', 'Redirected'),
            ('returned', 'Returned'),
            ('canceled', 'Canceled'),
        ],
        string="Aras Delivery State",
        readonly=True,
        copy=False,
    )
    aras_is_cod = fields.Boolean(string="Cash on Delivery")
    aras_cod_amount = fields.Float(string="COD Amount")
    aras_cod_type = fields.Selection(
        [('0', 'Cash'), ('1', 'Credit Card')],
        string="COD Type",
        default='0',
    )
    aras_delivery_person = fields.Char(
        string="Delivered To",
        readonly=True,
        copy=False,
    )
    aras_last_sync_warning = fields.Text(
        string="Aras Warning",
        readonly=True,
        copy=False,
    )
    aras_delivery_date = fields.Char(
        string="Delivery Date",
        readonly=True,
        copy=False,
    )
    aras_return_reason = fields.Char(
        string="Return / Transfer Reason",
        readonly=True,
        copy=False,
    )

    @api.model
    def _aras_sync_pickings(self):
        cutoff = fields.Datetime.now() - timedelta(days=15)
        pickings = self.search([
            ('aras_sync_pending', '=', True),
            ('aras_integration_code', '!=', False),
            ('date_done', '>', cutoff),
        ])
        if not pickings:
            return

        _logger.info("Aras Kargo cron: %d shipments to sync.", len(pickings))

        for picking in pickings:
            try:
                with self.env.cr.savepoint():
                    picking.carrier_id.aras_tracking_state_update(picking)
            except Exception as e:
                _logger.error(
                    "Aras cron error - Picking %s (ID: %s): %s",
                    picking.name, picking.id, e,
                )

    def send_to_shipper(self):
        self.ensure_one()
        if self.delivery_type != 'aras':
            return super().send_to_shipper()

        if self.aras_integration_code and self.aras_delivery_state != 'canceled':
            _logger.info(
                "Aras shipment already registered for %s (%s), skipping duplicate send.",
                self.name,
                self.aras_integration_code,
            )
            return

        res = self.carrier_id.send_shipping(self)[0]
        if self.carrier_id.free_over and self.sale_id:
            amount_without_delivery = self.sale_id._compute_amount_total_without_delivery()
            if self.carrier_id._compute_currency(
                self.sale_id, amount_without_delivery, 'pricelist_to_company'
            ) >= self.carrier_id.amount:
                res['exact_price'] = 0.0

        self.carrier_price = self.carrier_id.with_context(order=self.sale_id)._apply_margins(
            res['exact_price']
        )
        order_currency = self.sale_id.currency_id or self.company_id.currency_id
        msg = _(
            "Shipment registered in Aras Kargo with integration code %(code)s.",
            code=self.aras_integration_code or '-',
        )
        msg += Markup("<br/>") + _(
            "Tracking reference will be available after the shipment barcode is scanned."
        )
        msg += Markup("<br/>") + _(
            "Cost: %(price).2f %(currency)s",
            price=self.carrier_price,
            currency=order_currency.name,
        )
        self.message_post(body=msg)
        self._add_delivery_cost_to_so()

    def action_cancel_aras_shipment(self):
        self.ensure_one()
        if self.delivery_type != 'aras':
            return
        if not self.aras_integration_code:
            raise UserError(_("This shipment does not have an Aras integration code."))

        self.carrier_id.aras_cancel_shipment(self)
        self.write({
            'carrier_tracking_ref': False,
            'aras_integration_code': False,
            'aras_barcode_numbers': False,
            'aras_sync_pending': False,
            'aras_delivery_state': 'canceled',
            'aras_last_sync_warning': False,
            'aras_delivery_person': False,
            'aras_delivery_date': False,
            'aras_return_reason': False,
        })
