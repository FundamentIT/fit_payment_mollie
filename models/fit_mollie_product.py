from odoo import models, fields, api


class FitProduct(models.Model):
    _name = 'product.template'
    _inherit = ['product.template']

    mollie_subscription_duration = fields.Char(string='Incasso #', default=6)