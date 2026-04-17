# -*- coding: utf-8 -*-
{
    'name': 'SMS Verimor',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Verimor SMS Gateway — pure SMS sending integration',
    'author': 'ESKA, Odoo Community Association (OCA)',
    'website': 'https://www.eskayazilim.com.tr',
    'license': 'LGPL-3',
    'depends': [
        'sms',
        'iap',
    ],
    'data': [
        'views/iap_account_views.xml',
    ],
}
