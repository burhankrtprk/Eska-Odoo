{
    'name': 'Aras Kargo Integration',
    'summary': 'Aras Kargo shipping and reporting integration',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'author': 'ESKA',
    'license': 'AGPL-3',
    'depends': [
        'delivery',
        'stock',
        'stock_delivery',
    ],
    'external_dependencies': {
        'python': [
            'zeep',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/aras_delivery_data.xml',
        'data/aras_cron.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'reports/aras_shipping_report.xml',
    ],
}
