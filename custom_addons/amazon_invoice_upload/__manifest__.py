{
    'name':'Amazon Invoice Uploader',
    'version':'18.0',
    'category':'Accounting',
    'summary':'Uploads Odoo invoices using Amazon SP-API',
    'depends':['base', 'account', 'sale_amazon'],
    'data':[
        'views/account_move_view.xml',
    ],
    'installable':True,
    'application':False,
    'license':'LGPL-3',
}
