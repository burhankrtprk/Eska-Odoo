{
    'name': 'Amazon Invoice Uploader',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Uploads Odoo invoices using Amazon SP-API',
    'author': 'ESKA',
    'depends': ['base', 'account', 'sale_amazon'],
    'data': [
        'views/account_move_view.xml',
    ],
    'license': 'LGPL-3',
}
