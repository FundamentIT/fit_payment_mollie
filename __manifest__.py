# -*- encoding: utf-8 -*-

{
    'name': 'FIT Mollie Payment Acquirer',
    'version': '1.0',
    'author': 'Fundament IT',
    'website': 'https://fundament.it',
    'category': 'eCommerce',
    'description': "",
    'depends': ['payment','website_sale','payment_mollie_official','product_contract'],
    'data': [
        'security/ir.model.access.csv',
        'views/templates.xml',
        'views/fit_mollie_payment_acquirer.xml',
        'views/fit_mollie_product_template_view.xml',
        'views/fit_mollie_res_partner_view.xml',
        'views/fit_mollie_sale_order_view.xml',
    ],
    'installable': True,
    'currency': 'EUR',
    'images': ['images/main_screenshot.png']
}

