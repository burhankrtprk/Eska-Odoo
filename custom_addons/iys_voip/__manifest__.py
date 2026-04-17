# -*- coding: utf-8 -*-
{
    'name': 'IYS VoIP',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'IYS ARAMA consent blocking for Odoo VoIP',
    'author': 'ESKA, Odoo Community Association (OCA)',
    'website': 'https://www.eskayazilim.com.tr',
    'license': 'LGPL-3',
    'depends': [
        'iys',
        'voip',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
    ],
}
