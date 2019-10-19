# -*- coding: utf-'8' "-*-"

import json
import logging
from hashlib import sha256
import urlparse
import unicodedata
import pprint
import requests
import decimal
import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.tools.float_utils import float_compare
from odoo.tools.translate import _
from odoo.exceptions import ValidationError, RedirectWarning
from ...payment_mollie_official.models import mollie
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class FitAcquirerMollie(models.Model):
    _name = 'payment.acquirer'
    _inherit = ['payment.acquirer']

    mollie_incasso_type = fields.Selection([
        ('months', 'Per Maand'),
        ('days', 'Per Dag')], string='Incasso type',
        default='months', required=True)

class FitTxMollie(mollie.TxMollie):
    _subscription_url = '/payment/mollie/subscription/'

    @api.model
    def form_feedback(self, data, acquirer_name):
        _logger.info('FIT MOLLIE form_feedback 1!')
        result = super(FitTxMollie, self).form_feedback(data, acquirer_name)
        _logger.info('FIT MOLLIE form_feedback 2!')

    def _confirm_so(self, acquirer_name=False):
        _logger.info('FIT MOLLIE _confirm_so 1!')
        super(FitTxMollie, self)._confirm_so(acquirer_name)
        auto_payment_success = self._create_automatic_payment(acquirer_name)
        #if auto_payment_success:
        _logger.info('FIT MOLLIE _confirm_so automatic payment successful: %s', auto_payment_success)

    def _create_automatic_payment(self, acquirer_name):
        is_contract = False
        mollie_is_success = False
        try:
            is_contract = self.sale_order_id.order_line[0].product_id.is_contract
            _logger.info('FIT MOLLIE: validated if product is contract: %s', is_contract)
        except:
            _logger.info('FIT MOLLIE: unable to validate if product is contract, set is_contract to False.')

        if is_contract:
            try:
                if self._is_valid_mollie_mandate():

                    acquirer = self.acquirer_id
                    amount = self.sale_order_id.amount_total
                    mollie_customer_id = self.sale_order_id.partner_id.mollie_customer_id

                    _logger.info('FIT MOLLIE: try to create mollie subscription')
                    mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
                    url = "https://api.mollie.com/v2/customers/%s/subscriptions" % (mollie_customer_id)
                    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    contract = self.sale_order_id.project_id
                    subscription_start = datetime.datetime.strptime(contract.recurring_next_date, '%Y-%m-%d')
                    interval = "1 %s" % (acquirer.mollie_incasso_type)
                    if acquirer.mollie_incasso_type == 'days':
                        subscription_start = subscription_start + relativedelta(days=+1)
                    else:
                        subscription_start = subscription_start + relativedelta(months=+1)

                    payload = {
                        "amount": {
                            "currency": "EUR",
                            "value": "{:0,.2f}".format(decimal.Decimal(str(amount)))
                        },
                        "description": "Automatische Incasso BCNL %s" % self.sale_order_id.display_name,
                        "interval": interval,
                        "mandateId": self.mollie_mandate,
                        "startDate": subscription_start.strftime('%Y-%m-%d'),
                        "times": int(self.sale_order_id.product_id.mollie_subscription_duration)-1,
                        "webhookUrl": "%s%s?iscontract=%s&contract_id=%s" % (base_url, self._subscription_url, True, contract.id-1),
                        "metadata": {
                            "acquirer_id": self.acquirer_id.id,
                            "contract_id": contract.id-1
                        }
                    }
                    headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}

                    mollie_response = requests.post(
                        url, data=json.dumps(payload), headers=headers).json()

                    try:
                        mollie_subscription_id = mollie_response['id']
                        mollie_is_success = True
                    except:
                        mollie_is_success = False

                    if mollie_is_success:
                        _logger.info('FIT MOLLIE: successfully created Mollie subscription, id: %s, response: %s', mollie_subscription_id,
                                     mollie_response)
                        self.sale_order_id.partner_id.mollie_subscription_id = mollie_subscription_id
                    else:
                        _logger.error('FIT MOLLIE: error while creating Mollie subscription, result "%s", description %s, reponse %s',
                                     mollie_response['status'],
                                     mollie_response['detail'], mollie_response)
                        error_msg = 'Er is een fout opgetreden tijdens het aanmaken van de automatische incasso voor contract %s, details: %s' % (contract.id, mollie_response)
                        self.sale_order_id.partner_id.message_post(body=error_msg)
            except Exception as e:
                _logger.info('FIT MOLLIE: error while handling recurring payment: %s',e)
        else:
            _logger.info('FIT MOLLIE: not a contract, stop creating of recurring payment.')

        return mollie_is_success

    def _is_valid_mollie_mandate(self):
        mollie_customer_id = self.sale_order_id.partner_id.mollie_customer_id
        acquirer = self.acquirer_id

        _logger.info('FIT MOLLIE: try to retrieve customer mandate')
        mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
        url = "https://api.mollie.com/v2/customers/%s/mandates" % (mollie_customer_id)
        payload = {}
        headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}

        mollie_response = requests.get(
            url, data=json.dumps(payload), headers=headers).json()

        found_valid_mandate = False
        for mandate in mollie_response['_embedded']['mandates']:
            if mandate['status'] == 'valid':
                found_valid_mandate = True
                self.mollie_mandate = mandate['id']
                break

        if found_valid_mandate:
            _logger.info('FIT MOLLIE: Valid Mollie mandate, customer %s', mollie_customer_id)
            return True
        else:
            _logger.error('FIT MOLLIE: Invalid Mollie mandate, unable to set recurring payment for customer %s.', mollie_customer_id)
            return False
