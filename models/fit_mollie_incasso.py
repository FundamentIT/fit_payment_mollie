import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import fields, models, api

_logger = logging.getLogger(__name__)


class FitMollieIncasso(models.Model):
    _name = 'fit.mollie.incasso'
    _description = 'Incasso'

    mollie_incasso_partner = fields.Many2one(comodel_name='res.partner', string='incasso_partner')
    mollie_incasso_start = fields.Date('Start incasso')
    mollie_incasso_end = fields.Date('Eind incasso')
    mollie_incasso_product = fields.Many2one('product.template', string='Product', copy=False)
    mollie_incasso_contract = fields.Many2one('account.analytic.account', string='Contract', copy=False)

