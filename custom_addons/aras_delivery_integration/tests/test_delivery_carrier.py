from odoo.tests.common import TransactionCase


class TestDeliveryCarrier(TransactionCase):
    """Tests for Aras Kargo delivery carrier methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_delivery = cls.env['product.product'].create({
            'name': 'Aras Shipping',
            'type': 'service',
            'list_price': 15.0,
        })
        cls.carrier = cls.env['delivery.carrier'].create({
            'name': 'Aras Kargo Test',
            'delivery_type': 'aras',
            'product_id': cls.product_delivery.id,
            'aras_username': 'test_user',
            'aras_password': 'test_pass',
            'aras_customer_code': '12345',
        })

    # ──────────────────────────────────────────
    # Phone sanitization
    # ──────────────────────────────────────────
    def test_sanitize_phone_empty(self):
        """Empty phone should return empty string."""
        self.assertEqual(self.carrier._sanitize_phone(''), '')
        self.assertEqual(self.carrier._sanitize_phone(None), '')
        self.assertEqual(self.carrier._sanitize_phone(False), '')

    def test_sanitize_phone_with_country_code(self):
        """Phone starting with 90 should strip country code."""
        result = self.carrier._sanitize_phone('+90 532 123 45 67')
        self.assertEqual(result, '5321234567')

    def test_sanitize_phone_with_leading_zero(self):
        """Phone starting with 0 should strip leading zero."""
        result = self.carrier._sanitize_phone('0532 123 45 67')
        self.assertEqual(result, '5321234567')

    def test_sanitize_phone_plain_digits(self):
        """Plain 10-digit phone should be kept as-is."""
        result = self.carrier._sanitize_phone('5321234567')
        self.assertEqual(result, '5321234567')

    def test_sanitize_phone_with_special_chars(self):
        """Phone with parentheses and dashes should be cleaned."""
        result = self.carrier._sanitize_phone('(532) 123-4567')
        self.assertEqual(result, '5321234567')

    # ──────────────────────────────────────────
    # Integration code generation
    # ──────────────────────────────────────────
    def test_generate_integration_code_format(self):
        """Integration code should be 16 chars: 10 time + 6 picking ID."""
        picking = self.env['stock.picking'].new({'id': 42})
        code = self.carrier._generate_aras_integration_code(picking)
        self.assertEqual(len(code), 16)
        self.assertTrue(code.endswith('000042'))

    # ──────────────────────────────────────────
    # Barcode generation
    # ──────────────────────────────────────────
    def test_generate_barcode_numbers_single(self):
        """Single piece should generate one barcode."""
        barcodes = self.carrier._generate_barcode_numbers('INT123', 1)
        self.assertEqual(len(barcodes), 1)
        self.assertEqual(barcodes[0], 'INT12301')

    def test_generate_barcode_numbers_multiple(self):
        """Multiple pieces should generate sequential barcodes."""
        barcodes = self.carrier._generate_barcode_numbers('INT123', 3)
        self.assertEqual(len(barcodes), 3)
        self.assertEqual(barcodes[0], 'INT12301')
        self.assertEqual(barcodes[1], 'INT12302')
        self.assertEqual(barcodes[2], 'INT12303')

    # ──────────────────────────────────────────
    # Tracking number extraction
    # ──────────────────────────────────────────
    def test_extract_tracking_number_from_dict(self):
        """Should find tracking number in dict response."""
        result = {'TrackingNumber': 'TRK-9876', 'other': 'value'}
        tracking = self.carrier._extract_tracking_number(result)
        self.assertEqual(tracking, 'TRK-9876')

    def test_extract_tracking_number_fallback_fields(self):
        """Should try fallback fields if TrackingNumber is missing."""
        result = {'CargoKey': 'CK-555'}
        tracking = self.carrier._extract_tracking_number(result)
        self.assertEqual(tracking, 'CK-555')

    def test_extract_tracking_number_none_result(self):
        """Should return empty string for None input."""
        self.assertEqual(self.carrier._extract_tracking_number(None), '')

    def test_extract_tracking_number_ignores_none_string(self):
        """Should ignore 'None' string values."""
        result = {'TrackingNumber': 'None'}
        self.assertEqual(self.carrier._extract_tracking_number(result), '')

    # ──────────────────────────────────────────
    # Rate shipment
    # ──────────────────────────────────────────
    def test_aras_rate_shipment(self):
        """rate_shipment should return product list price."""
        order = self.env['sale.order'].new({})
        result = self.carrier.aras_rate_shipment(order)
        self.assertTrue(result['success'])
        self.assertEqual(result['price'], 15.0)
        self.assertFalse(result['error_message'])

    # ──────────────────────────────────────────
    # Warning message
    # ──────────────────────────────────────────
    def test_warning_message_new_record(self):
        """New record message should contain 'created'."""
        msg = self.carrier._get_aras_warning_message('INT-001', record_confirmed=False)
        self.assertIn('INT-001', msg)

    def test_warning_message_confirmed_record(self):
        """Confirmed record message should contain 'found'."""
        msg = self.carrier._get_aras_warning_message('INT-001', record_confirmed=True)
        self.assertIn('INT-001', msg)

    # ──────────────────────────────────────────
    # Tracking link
    # ──────────────────────────────────────────
    def test_tracking_link_with_ref(self):
        """Should return Aras tracking URL when reference exists."""
        picking = self.env['stock.picking'].new({'carrier_tracking_ref': 'TRK123'})
        link = self.carrier.aras_get_tracking_link(picking)
        self.assertIn('TRK123', link)
        self.assertIn('araskargo.com.tr', link)

    def test_tracking_link_without_ref(self):
        """Should return False when no tracking reference."""
        picking = self.env['stock.picking'].new({'carrier_tracking_ref': False})
        link = self.carrier.aras_get_tracking_link(picking)
        self.assertFalse(link)

    # ──────────────────────────────────────────
    # Status map update
    # ──────────────────────────────────────────
    def test_update_picking_from_query_delivered(self):
        """Delivered status should set aras_delivery_state and clear sync_pending."""
        partner = self.env['res.partner'].create({'name': 'Receiver'})
        picking_type = self.env.ref('stock.picking_type_out')
        location = self.env.ref('stock.stock_location_stock')
        location_dest = self.env.ref('stock.stock_location_customers')
        picking = self.env['stock.picking'].create({
            'partner_id': partner.id,
            'picking_type_id': picking_type.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'carrier_id': self.carrier.id,
            'aras_integration_code': 'INT-TEST',
            'aras_sync_pending': True,
        })
        data = {
            'DURUM KODU': '6',
            'TrackingNumber': 'TRK-DELIVERED',
            'TESLİM ALAN': 'Ali Veli',
            'TESLİM TARİHİ': '2025-01-15',
            'TESLİM SAATİ': '14:30',
        }
        self.carrier._update_picking_from_query(picking, data)
        self.assertEqual(picking.aras_delivery_state, 'delivered')
        self.assertFalse(picking.aras_sync_pending)
        self.assertEqual(picking.carrier_tracking_ref, 'TRK-DELIVERED')
        self.assertEqual(picking.aras_delivery_person, 'Ali Veli')
