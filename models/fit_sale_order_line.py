# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# Copyright 2019 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
# pylint: disable=missing-docstring,protected-access
import datetime
import logging

from odoo import api, fields, models
from ...product_contract.models import sale_order_line
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class FitSaleOrderLine(sale_order_line.SaleOrderLine):
    _inherit = 'sale.order.line'

    @api.multi
    def create_contract(self):
        """Create contract for sale order line.

        Should be called on confirmation of sale order.
        """
        for line in self.filtered('product_id.is_contract'):
            contract_vals = line._prepare_contract_vals()
            contract = self.env['account.analytic.account'].create(
                contract_vals)
            line.contract_id = contract.id
            if self.order_id.payment_tx_id.acquirer_id.environment == 'test':
                _logger.info('FIT MOLLIE: Mollie test environment, start create recurring invoice')
                contract.recurring_create_invoice()

    @api.multi
    def _prepare_contract_vals(self):
        """Prepare values to create contract from template."""
        self.ensure_one()
        contract_tmpl = self.product_id.contract_template_id
        order = self.order_id
        contract_duration = int(self.product_id.mollie_subscription_duration)
        date_start_object = datetime.datetime.strptime(fields.Date.today(), '%Y-%m-%d')

        if order.payment_tx_id.acquirer_id.mollie_incasso_type == 'days':
            date_start_object = datetime.datetime.strptime(fields.Date.today(), '%Y-%m-%d') + relativedelta(days=-1)
            date_next_object = date_start_object
            date_end_object = date_start_object + relativedelta(days=+contract_duration)
        elif order.payment_tx_id.acquirer_id.mollie_incasso_type == 'months':
            date_next_object = date_start_object + relativedelta(months=+1) + relativedelta(days=-1)
            date_end_object = date_start_object + relativedelta(months=+contract_duration)

        contract = self.env['account.analytic.account'].new({
            'contract_template_id': contract_tmpl.id,
            'date_start':  date_start_object,
            'date_end': date_end_object,
            'name': '%s Contract' % order.name,
            'partner_id': order.partner_id.id,
            'recurring_invoices': True,
            'recurring_next_date': date_next_object
        })

#        if order.payment_tx_id.acquirer_id.environment == 'test':
#            _logger.info('FIT MOLLIE: Mollie test environment, start create recurring invoice')
#            contract.recurring_create_invoice()

        _logger.info('FIT MOLLIE: created contract start date: %s, end date: %s, next invoice %s, contract project %s',
                    date_start_object, date_end_object, date_next_object, contract.name)
        contract._onchange_contract_template_id()
        return contract._convert_to_write(contract._cache)
