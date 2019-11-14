import json
import logging
import requests
from odoo import models, fields, api, http, _

_logger = logging.getLogger(__name__)


class FitMolliePartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner']

    mollie_customer_id = fields.Char(string='Mollie Customer ID')
    mollie_subscription_id = fields.Char(string='Mollie Subscription ID')
    mollie_incasso_view = fields.Text(compute='_compute_incasso_overview', string='Incasso overzicht')

    @api.model
    def _compute_incasso_overview(self):
        for partner in self:
            if partner.id <> 1 and partner.mollie_customer_id:
                self._get_incasso_data_mollie(partner)

    @api.multi
    def cancel_mollie_subscriptions(self):
        try:
            for partner in self:
                if partner.id <> 1 and partner.mollie_customer_id:
                    self._get_incasso_data_mollie(partner)
                    _logger.info('FIT MOLLIE: cancel subscription, start retrieving existing automatic payments for partner %s with mollie id '
                                 '%s',
                                 partner.name,
                         partner.mollie_customer_id)
                    acquirer = partner.env['payment.acquirer'].search([('provider', '=', 'mollie')], limit=1)
                    mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
                    url = "https://api.mollie.com/v2/customers/%s/subscriptions" % (partner.mollie_customer_id)
                    payload = {}
                    headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}
                    mollie_response = requests.get(url, data=json.dumps(payload), headers=headers).json()

                    _logger.info('FIT MOLLIE: cancel subscription, result Mollie Subscriptions: %s', mollie_response)
                    try:
                        mollie_status = mollie_response['count']
                        mollie_is_success = True
                    except:
                        mollie_is_success = False

                    if mollie_is_success:
                        for mollie_incasso in mollie_response['_embedded']['subscriptions']:
                            _logger.info('FIT MOLLIE: cancel subscription, incasso aanwezig: %s, details: %s', mollie_incasso['id'],
                                         mollie_incasso)
                            if mollie_incasso['status'] == 'active':
                                _logger.info('FIT MOLLIE: cancel subscription, is een actieve incasso, start annuleren')
                                #url = "https://api.mollie.com/v2/customers/%s/subscriptions/%s", (str(partner.mollie_customer_id),
                                #                                                                      str(mollie_incasso['id']))
                                url = "https://api.mollie.com/v2/customers/"+str(partner.mollie_customer_id)+"/subscriptions/"+str(mollie_incasso['id'])
                                mollie_cancel_response = requests.delete(url, data=json.dumps(payload), headers=headers).json()
                                _logger.info('FIT MOLLIE: cancel subscription, result Mollie: %s', mollie_cancel_response)
                                if mollie_cancel_response['status'] == "canceled":
                                    _logger.info('FIT MOLLIE: cancel subscription successfully cancelled, stop related contract')
                                    contract_id = mollie_cancel_response['metadata']['contract_id']
                                    if contract_id:
                                        _logger.info('FIT MOLLIE: cancel subscription set contract id %s to inactive (toggle_archive())', contract_id)
                                        contract = self.env['account.analytic.account'].sudo().browse(contract_id)
                                        if contract:
                                            contract.toggle_active()
                                            _logger.info('FIT MOLLIE: cancel subscription deactivated contract id %s', contract_id)
        except BaseException as e:
            raise

    def _get_incasso_data_mollie(self,partner):
        _logger.info('FIT MOLLIE: start retrieving existing automatic payments for partner %s with mollie id %s', partner.name, partner.mollie_customer_id)

        acquirer = partner.env['payment.acquirer'].search([('provider', '=', 'mollie')], limit=1)
        mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
        url = "https://api.mollie.com/v2/customers/%s/subscriptions" % (partner.mollie_customer_id)
        payload = {}
        #if acquirer.environment == 'test':
        #    payload["testmode"] = True
        headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}
        mollie_response = requests.get(url, data=json.dumps(payload), headers=headers).json()

        _logger.info('FIT MOLLIE: Result Mollie Subscriptions: %s', mollie_response)
        mollie_incasso_view_text = ''
        try:
            mollie_status = mollie_response['count']
            mollie_is_success = True
        except:
            mollie_is_success = False

        if mollie_is_success:
            mollie_incasso_view_text = 'Aantal Mollie Incasso: %s\n' % (mollie_response['count'])
            for mollie_incasso in mollie_response['_embedded']['subscriptions']:
                _logger.info('FIT MOLLIE: incasso aanwezig: %s, details: %s', mollie_incasso['id'], mollie_incasso)
                mollie_incasso_view_text = mollie_incasso_view_text + '\nIncasso "%s", status: %s' % (mollie_incasso['id'], mollie_incasso[
                    'status'])
                #mollie_subscription_details = self._get_mollie_subscription_details(mollie_incasso, headers)
                if 'nextPaymentDate' in mollie_incasso:
                    next_payment_date = mollie_incasso['nextPaymentDate']
                else:
                    next_payment_date = 'geen'

                mollie_incasso_view_text = mollie_incasso_view_text + '\n\t - Betreft: %s\n\t - Start datum: %s \n\t - Aantal totaal: %s \n\t ' \
                                                                      '- Aantal over: %s\n\t - Volgende afschrijving: %s \n' % (
                    mollie_incasso['description'], mollie_incasso['startDate'], mollie_incasso['times'], mollie_incasso['timesRemaining'],
                    next_payment_date)
                _logger.info('FIT MOLLIE: incasso aanwezig: %s', mollie_incasso)
        else:
            mollie_incasso_view_text = 'Er is een fout opgetreden tijdens de communicatie met Molle: %s, details: %s\n' % ((mollie_response[
            'status']), mollie_response['detail'])

        partner.mollie_incasso_view = mollie_incasso_view_text

    def _get_mollie_subscription_details(self, mollie_incasso, headers):
        url = mollie_incasso['_links']['self']['href']
        payload = {}
        if url:
            mollie_response = requests.get(url, data=json.dumps(payload), headers=headers).json()
            _logger.info('FIT MOLLIE: Result Mollie Subscription Details: %s', mollie_response)
            return mollie_response


    """
    
    @api.model
    def default_get(self, fields_list):
        res = super(FitMolliePartner, self).default_get(fields)
        vals = [(0, 0, {
            'mollie_incasso_partner': self.id,
            'mollie_incasso_start': fields.Date.today(),
            'mollie_incasso_end': fields.Date.today(),
            'mollie_incasso_product': '',
            'mollie_incasso_contract': '',
        })]
        res.update({'mollie_incasso': vals})
        return res

    

#    mollie_incasso = fields.One2many(comodel_name='fit.mollie.incasso', inverse_name='mollie_incasso_partner', string='Mollie Incasso',
 #                                       store='False', default=_compute_mollie_incasso)
    mollie_incasso = fields.One2many(comodel_name='fit.mollie.incasso', inverse_name='mollie_incasso_partner', string='Mollie Incasso')
    #, default=(0,0,{'mollie_incasso_partner': 1, 'mollie_incasso_start': fields.Date.today(),
`    #                                                                 'mollie_incasso_end': fields.Date.today(), 'mollie_incasso_product': '',
    #                                                                 'mollie_incasso_contract': ''})

    def _compute_total_incasso(self):
        counter = 0
        for mollie_incasso in self.mollie_incasso:
            counter += 1
        _logger.info('FIT MOLLIE: counted Mollie Incasso entries: %s', counter)
        self.mollie_incasso_count = counter


    """