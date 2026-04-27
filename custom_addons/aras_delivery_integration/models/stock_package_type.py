# Copyright 2026 ESKA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Aras Kargo paket tipi genişletmesi."""

from odoo import fields, models


class PackageType(models.Model):
    """Paket tipine Aras Kargo taşıyıcı seçeneği ekler."""

    _inherit = 'stock.package.type'

    package_carrier_type = fields.Selection(
        selection_add=[('aras', 'Aras Kargo')],
        ondelete={'aras': 'set default'}
    )