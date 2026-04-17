import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.sale_amazon import utils as amazon_utils


class AccountMove(models.Model):
    _inherit = 'account.move'

    amazon_upload_status = fields.Selection(
    [
        ('draft', 'Draft'),
        ('sent', 'Sent to Amazon'),
        ('error', 'Error')
    ],
        string='Amazon Status',
        default='draft',
        copy=False
    )

    amazon_order_reference = fields.Char(
        string='Amazon Order Ref',
        compute='_compute_amazon_order_reference',
        store=True,
        readonly=True
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id.amazon_order_ref')
    def _compute_amazon_order_reference(self):
        for move in self:
            sale_orders = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            amazon_orders = sale_orders.filtered(lambda o: o.amazon_order_ref)

            if amazon_orders:
                move.amazon_order_reference = amazon_orders[0].amazon_order_ref
            else:
                move.amazon_order_reference = False

    def _get_related_amazon_sale_orders(self):
        self.ensure_one()
        return self.invoice_line_ids.mapped('sale_line_ids.order_id').filtered('amazon_order_ref')

    def _get_related_amazon_sale_lines(self):
        self.ensure_one()
        return self.invoice_line_ids.mapped('sale_line_ids').filtered('amazon_offer_id')

    def _get_related_amazon_account(self):
        self.ensure_one()
        amazon_sale_lines = self._get_related_amazon_sale_lines()

        if not amazon_sale_lines:
            raise UserError(_("No linked Amazon order found for this invoice."))

        accounts = amazon_sale_lines.mapped('amazon_offer_id.account_id')
        if not accounts:
            raise UserError(_("No Amazon account found for this invoice."))

        if len(accounts) > 1:
            raise UserError(_("This invoice is linked to multiple Amazon accounts."))

        amazon_orders = self._get_related_amazon_sale_orders()

        if len(amazon_orders) > 1:
            raise UserError(_("This invoice is linked to multiple Amazon orders."))

        return accounts[0], amazon_orders[0].amazon_order_ref

    def _get_amazon_marketplace_ref(self, account):
        self.ensure_one()

        amazon_sale_lines = self._get_related_amazon_sale_lines()
        marketplaces = amazon_sale_lines.mapped('amazon_offer_id.marketplace_id')

        if len(marketplaces) > 1:
            raise UserError(_("This invoice is linked to multiple Amazon marketplaces."))

        if marketplaces:
            return marketplaces[0].api_ref

        return account.base_marketplace_id.api_ref

    def _generate_invoice_pdf(self):
        self.ensure_one()
        pdf_content, dummy = self.env['ir.actions.report']._render_qweb_pdf('account.report_invoice', [self.id])

        if not pdf_content:
            raise UserError(_("Could not generate PDF."))

        return pdf_content

    def _create_amazon_feed_document(self, account):
        payload_doc = {'contentType': 'application/pdf'}
        return amazon_utils.make_sp_api_request(
            account,
            'createFeedDocument',
            payload=payload_doc,
            method='POST'
        )

    def _upload_pdf_to_amazon(self, upload_url, pdf_content):
        headers = {'Content-Type': 'application/pdf'}
        try:
            response = requests.put(
                upload_url,
                data=pdf_content,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
        except Exception as e:
            raise UserError(_("Failed to upload PDF to Amazon: %s") % str(e))

    def _submit_amazon_invoice_feed(self, account, marketplace_ref, feed_document_id, amazon_order_ref, invoice_number,
                                    total_amount, total_vat):
        payload_feed = {
            'feedType': 'UPLOAD_VAT_INVOICE',
            'marketplaceIds': [marketplace_ref],
            'inputFeedDocumentId': feed_document_id,
            'feedOptions': {
                'metadata:orderid': amazon_order_ref,
                'metadata:invoicenumber': invoice_number,
                'metadata:documenttype': 'Invoice',
                'metadata:totalamount': str(total_amount),
                'metadata:totalvatamount': str(total_vat)
            }
        }
        return amazon_utils.make_sp_api_request(
            account,
            'createFeed',
            payload=payload_feed,
            method='POST'
        )

    def action_upload_to_amazon(self):
        self.ensure_one()

        account, amazon_order_ref = self._get_related_amazon_account()
        marketplace_ref = self._get_amazon_marketplace_ref(account)

        formatted_total_amount = "{:.2f}".format(self.amount_total)
        formatted_total_vat = "{:.2f}".format(self.amount_tax)

        try:
            doc_response = self._create_amazon_feed_document(account)
            feed_document_id = doc_response.get('feedDocumentId')
            upload_url = doc_response.get('url')

            pdf_content = self._generate_invoice_pdf()
            self._upload_pdf_to_amazon(upload_url, pdf_content)

            self._submit_amazon_invoice_feed(
                account,
                marketplace_ref,
                feed_document_id,
                amazon_order_ref,
                self.name,
                formatted_total_amount,
                formatted_total_vat
            )

            self.write({'amazon_upload_status': 'sent'})

        except Exception as e:
            self.write({'amazon_upload_status': 'error'})
            raise UserError(str(e))
