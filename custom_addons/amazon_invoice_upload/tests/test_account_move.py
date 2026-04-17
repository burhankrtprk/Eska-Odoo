from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestAccountMoveAmazon(TransactionCase):
    """Tests for Amazon Invoice Upload functionality on account.move."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
        })

    # ──────────────────────────────────────────
    # Field defaults
    # ──────────────────────────────────────────
    def test_amazon_upload_status_default(self):
        """New invoices should have amazon_upload_status = draft."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        self.assertEqual(move.amazon_upload_status, 'draft')

    def test_amazon_order_reference_no_sale(self):
        """Invoice without sale orders should have empty amazon_order_reference."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        self.assertFalse(move.amazon_order_reference)

    # ──────────────────────────────────────────
    # Validation: no linked Amazon order
    # ──────────────────────────────────────────
    def test_get_related_amazon_account_no_lines(self):
        """Should raise UserError when invoice has no Amazon-linked sale lines."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        with self.assertRaises(UserError):
            move._get_related_amazon_account()

    # ──────────────────────────────────────────
    # Upload action — error path
    # ──────────────────────────────────────────
    def test_action_upload_sets_error_on_failure(self):
        """action_upload_to_amazon should set status to 'error' on failure."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        with self.assertRaises(UserError):
            move.action_upload_to_amazon()
        self.assertEqual(move.amazon_upload_status, 'error')

    # ──────────────────────────────────────────
    # Upload action — success path (mocked)
    # ──────────────────────────────────────────
    def test_action_upload_success_mocked(self):
        """Successful upload should set status to 'sent' (all external calls mocked)."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        mock_account = MagicMock()
        mock_account.base_marketplace_id.api_ref = 'A1RKKUPIHCS9HS'

        with patch.object(type(move), '_get_related_amazon_account',
                          return_value=(mock_account, 'ORDER-123')), \
             patch.object(type(move), '_get_amazon_marketplace_ref',
                          return_value='A1RKKUPIHCS9HS'), \
             patch.object(type(move), '_create_amazon_feed_document',
                          return_value={'feedDocumentId': 'DOC-1', 'url': 'https://example.com/upload'}), \
             patch.object(type(move), '_generate_invoice_pdf',
                          return_value=b'%PDF-fake-content'), \
             patch.object(type(move), '_upload_pdf_to_amazon'), \
             patch.object(type(move), '_submit_amazon_invoice_feed'):
            move.action_upload_to_amazon()

        self.assertEqual(move.amazon_upload_status, 'sent')

    # ──────────────────────────────────────────
    # Copy should reset status
    # ──────────────────────────────────────────
    def test_copy_resets_upload_status(self):
        """Duplicating an invoice should reset amazon_upload_status to draft."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        move.amazon_upload_status = 'sent'
        new_move = move.copy()
        self.assertEqual(new_move.amazon_upload_status, 'draft')
