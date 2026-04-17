# -*- coding: utf-8 -*-
{
    'name': 'IYS',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'IYS (İleti Yönetim Sistemi) base consent management',
    'author': 'ESKA, Odoo Community Association (OCA)',
    'website': 'https://www.eskayazilim.com.tr',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'iap',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/iap_account_views.xml',
        'views/res_partner_views.xml',
        'views/iys_push_queue_views.xml',
    ],
}
