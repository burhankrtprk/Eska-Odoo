from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestStockPickingAras(TransactionCase):
    """Tests for Aras Kargo fields and actions on stock.picking."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
            'phone': '05321234567',
        })
        cls.product_delivery = cls.env['product.product'].create({
            'name': 'Aras Shipping',
            'type': 'service',
            'list_price': 10.0,
        })
        cls.carrier = cls.env['delivery.carrier'].create({
            'name': 'Aras Test',
            'delivery_type': 'aras',
            'product_id': cls.product_delivery.id,
            'aras_username': 'user',
            'aras_password': 'pass',
            'aras_customer_code': '99999',
        })
        cls.picking_type = cls.env.ref('stock.picking_type_out')
        cls.location = cls.env.ref('stock.stock_location_stock')
        cls.location_dest = cls.env.ref('stock.stock_location_customers')

    def _create_picking(self, **kwargs):
        vals = {
            'partner_id': self.partner.id,
            'picking_type_id': self.picking_type.id,
            'location_id': self.location.id,
            'location_dest_id': self.location_dest.id,
            'carrier_id': self.carrier.id,
        }
        vals.update(kwargs)
        return self.env['stock.picking'].create(vals)

    # ──────────────────────────────────────────
    # Field defaults
    # ──────────────────────────────────────────
    def test_default_field_values(self):
        """New picking should have Aras fields at default values."""
        picking = self._create_picking()
        self.assertFalse(picking.aras_integration_code)
        self.assertFalse(picking.aras_barcode_numbers)
        self.assertFalse(picking.aras_sync_pending)
        self.assertFalse(picking.aras_delivery_state)
        self.assertFalse(picking.aras_is_cod)
        self.assertEqual(picking.aras_cod_amount, 0.0)

    # ──────────────────────────────────────────
    # Cancel without integration code
    # ──────────────────────────────────────────
    def test_cancel_without_integration_code_raises(self):
        """Canceling a picking without integration code should raise UserError."""
        picking = self._create_picking(delivery_type='aras')
        with self.assertRaises(UserError):
            picking.action_cancel_aras_shipment()

    def test_cancel_non_aras_picking_does_nothing(self):
        """Canceling a non-Aras picking should do nothing."""
        fixed_carrier = self.env['delivery.carrier'].create({
            'name': 'Fixed Carrier',
            'delivery_type': 'fixed',
            'product_id': self.product_delivery.id,
        })
        picking = self._create_picking(carrier_id=fixed_carrier.id)
        result = picking.action_cancel_aras_shipment()
        self.assertIsNone(result)

    # ──────────────────────────────────────────
    # Copy should not carry Aras fields
    # ──────────────────────────────────────────
    def test_copy_resets_aras_fields(self):
        """Duplicating a picking should reset Aras-specific fields."""
        picking = self._create_picking()
        picking.write({
            'aras_integration_code': 'INT-COPY-TEST',
            'aras_barcode_numbers': 'BC001,BC002',
            'aras_sync_pending': True,
        })
        new_picking = picking.copy()
        self.assertFalse(new_picking.aras_integration_code)
        self.assertFalse(new_picking.aras_barcode_numbers)
        self.assertFalse(new_picking.aras_sync_pending)

    # ──────────────────────────────────────────
    # Delivery state transitions
    # ──────────────────────────────────────────
    def test_write_delivery_state(self):
        """Should be able to write all valid delivery states."""
        picking = self._create_picking()
        valid_states = [
            'at_departure', 'in_transit', 'at_delivery_branch',
            'out_for_delivery', 'partial_delivery', 'delivered',
            'redirected', 'returned', 'canceled',
        ]
        for state in valid_states:
            picking.write({'aras_delivery_state': state})
            self.assertEqual(picking.aras_delivery_state, state)

    # ──────────────────────────────────────────
    # COD fields
    # ──────────────────────────────────────────
    def test_cod_fields(self):
        """COD fields should be writable and readable."""
        picking = self._create_picking()
        picking.write({
            'aras_is_cod': True,
            'aras_cod_amount': 250.50,
            'aras_cod_type': '1',
        })
        self.assertTrue(picking.aras_is_cod)
        self.assertEqual(picking.aras_cod_amount, 250.50)
        self.assertEqual(picking.aras_cod_type, '1')
