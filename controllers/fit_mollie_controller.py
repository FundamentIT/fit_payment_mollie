# -*- coding: utf-8 -*-

import json
import logging
import requests
import werkzeug
import pprint
import locale
import decimal
import datetime

from psycopg2.psycopg1 import cursor

from odoo import http, SUPERUSER_ID, fields, _
from odoo.http import request, Response
from odoo.exceptions import ValidationError
from ...payment_mollie_official.controllers import main
from odoo.addons.website_sale.controllers import main as website_sale_main

_logger = logging.getLogger(__name__)


class FitMollieController(main.MollieController):
    _notify_url = '/payment/mollie/notify/'
    _redirect_url = '/payment/mollie/redirect/'
    _cancel_url = '/payment/mollie/cancel/'
    _subscription_url = '/payment/mollie/subscription/'

    @http.route('/accept_mollie_incasso', type='json', auth='public', website=True, csrf=False)
    def accept_mollie_incasso(self, **kw):
        sale_order_id = kw.get('sale_order_id')
        is_accepted = kw.get('is_accepted')
        sale_order = request.env['sale.order'].sudo().browse(int(sale_order_id))
        if sale_order:
            sale_order.write({"mollie_incasso_accept": is_accepted})

        _logger.debug('FIT_MOLLIE: received Mollie accept incasso for order: %s, accepted: %s', sale_order_id,is_accepted)


    @http.route([
        '/payment/mollie/notify'],
        type='http', auth='none', methods=['GET'])
    def mollie_notify(self, **post):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect("/shop/payment/validate")

    @http.route([
        '/payment/mollie/redirect'], type='http', auth="none", methods=['GET'])
    def mollie_redirect(self, **post):
        _logger.info('FIT_MOLLIE: received Mollie redirect')
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect("/shop/payment/validate")

    @http.route([
        '/payment/mollie/cancel'], type='http', auth="none", methods=['GET'])
    def mollie_cancel(self, **post):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect("/shop/payment/validate")

    @http.route([
        '/payment/mollie/intermediate'], type='http', auth="none", methods=['POST'], csrf=False)
    def mollie_intermediate(self, **post):
        _logger.info('FIT_MOLLIE: received Mollie intermediate: %s', post)
        acquirer = request.env['payment.acquirer'].browse(int(post['Key']))
        url = post['URL'] + "payments"
        headers = {'content-type': 'application/json',
                   'Authorization': 'Bearer ' + acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']}
        base_url = post['BaseUrl']
        orderid = post['OrderId']
        description = post['Description']
        currency = post['Currency']
        amount = post['Amount']
        language = post['Language']
        name = post['Name']
        email = post['Email']
        zip = post['Zip']
        address = post['Address']
        town = post['Town']
        country = post['Country']
        phone = post['Phone']
        is_contract = False
        product = None
        res_partner = None

        payment_transaction = request.env['payment.transaction'].sudo().search([('reference', '=', orderid)])
        if payment_transaction:
            sale_order = payment_transaction.sale_order_id
            res_partner = sale_order.partner_id
            for order_line in sale_order.order_line:
                for product_id in order_line.product_id:
                    is_contract = product_id.is_contract
                    _logger.info('FIT Mollie: found product, is contract: %s', is_contract)

        if is_contract:
            mollie_customer_id = self._get_customer_id(acquirer, res_partner)
            url = "https://api.mollie.com/v2/payments"
            payload = {
                "description": "Mandaat Automatische Incasso %s" % description,
                "amount": {
                    "currency": "EUR",
                    "value": "{:0,.2f}".format(decimal.Decimal(str(amount)))
                },
                "customerId": mollie_customer_id,
                "sequenceType": "first",
                "redirectUrl": "%s%s?iscontract=%s&reference=%s" % (base_url, self._redirect_url, is_contract, orderid),
            }
        else:
            payload = {
                "description": description,
                "amount": amount,
                # "webhookUrl": base_url + self._notify_url,
                "redirectUrl": "%s%s?iscontract=%s&reference=%s" % (base_url, self._redirect_url, is_contract, orderid),
                "metadata": {
                    "order_id": orderid,
                    "customer": {
                        "locale": language,
                        "currency": currency,
                        "last_name": name,
                        "address1": address,
                        "zip_code": zip,
                        "city": town,
                        "country": country,
                        "phone": phone,
                        "email": email
                    }
                }
            }

        mollie_response = requests.post(
            url, data=json.dumps(payload), headers=headers).json()
        _logger.debug('FIT MOLLIE: intermediate Mollie response: %s', mollie_response)

        if mollie_response["status"] == 410:
            _logger.error('FIT MOLLIE: invalid customer ID %s, clear customer id and redirect to payment to restart validation',
                          mollie_customer_id)
            res_partner.mollie_customer_id = ''
            return werkzeug.utils.redirect("/shop/payment")

        if mollie_response["status"] == "open":
            payment_tx = request.env['payment.transaction'].sudo().search([('reference', '=', orderid)])
            if not payment_tx or len(payment_tx) > 1:
                error_msg = ('received data for reference %s') % (pprint.pformat(orderid))
                if not payment_tx:
                    error_msg += ('; no order found')
                else:
                    error_msg += ('; multiple order found')
                _logger.info(error_msg)
                raise ValidationError(error_msg)
            payment_tx.write({"acquirer_reference": mollie_response["id"]})

            if is_contract:
                payment_url = mollie_response["_links"]["checkout"]["href"]
            else:
                payment_url = mollie_response["links"]["paymentUrl"]
            return werkzeug.utils.redirect(payment_url)

        return werkzeug.utils.redirect("/")

    @http.route([
        '/payment/mollie/subscription'], type='http', auth="none", methods=['POST'], csrf=False)
    def mollie_subscription(self, **post):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        _logger.info('FIT MOLLIE: Retrieved Mollie Subscription update: %s', post)
        acquirer = request.env['payment.acquirer'].search([('provider', '=', 'mollie')], limit=1)
        mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
        url = "https://api.mollie.com/v2/payments/%s" % (post['id'])
        payload = {}
        headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}

        mollie_response = requests.get(
            url, data=json.dumps(payload), headers=headers).json()
        _logger.info('FIT MOLLIE: Result Mollie Subscription Payment: %s', mollie_response)

        contract_id = post["contract_id"]
        account_journal = request.env['account.journal'].sudo().browse(int(acquirer.journal_id))
        if mollie_response["status"] == "paid":
            contract = request.env['account.analytic.account'].sudo().search([("id", '=', contract_id)], limit=1)#, order='date_invoice asc'
            for account_invoice_id in sorted(contract.account_invoice_ids, reverse=True):
                _logger.info('FIT MOLLIE: Handle invoice %s fom contract %s', account_invoice_id.id, contract_id)
                account_invoice = request.env['account.invoice'].sudo().browse(int(account_invoice_id.id))
                if account_invoice.state == 'draft':
                    account_invoice.sudo().action_invoice_open()
                    _logger.info('FIT MOLLIE: Set invoice %s state to "Open"', account_invoice.display_name)
                if account_invoice.state == 'open':
                    account_invoice.sudo().pay_and_reconcile(account_journal)
                    _logger.info('FIT MOLLIE: Set invoice %s state to "Paid"', account_invoice.display_name)
                    break

        _logger.info('FIT MOLLIE: Result Mollie Subscription payment status: %s', mollie_response)
        return Response("[]", status=200)

    def _get_customer_id(self, acquirer, partner):
        _logger.info('Checking Mollie customer ID for partner %s', partner.name)
        if not partner.mollie_customer_id:
            url = 'https://api.mollie.com/v2/customers'
            headers = {'content-type': 'application/json',
                       'Authorization': 'Bearer ' + acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']}
            payload = {
                "name": partner.name,
                "email": partner.email
            }

            mollie_response = requests.post(
                url, data=json.dumps(payload), headers=headers).json()

            partner.mollie_customer_id = mollie_response["id"]

        return partner.mollie_customer_id


class FitWebsiteSale(website_sale_main.WebsiteSale):
    # Set Valid/invalid flag to show/hide warning
    @http.route(['/shop/cart'], type='http', auth="public", website=True)
    def cart(self, **post):
        order = request.website.sale_get_order()
        valid_contract_amount = self._is_valid_contract_amount(order)
        valid_product = self._is_valid_products(order)
        active_contract = self._is_active_contract(order)
        contains_contract = self._contains_contract(order)
        subscription_accepted = order.mollie_incasso_accept

        if order:
            from_currency = order.company_id.currency_id
            to_currency = order.pricelist_id.currency_id
            compute_currency = lambda price: from_currency.compute(price, to_currency)
        else:
            compute_currency = lambda price: price

        values = {
            'website_sale_order': order,
            'compute_currency': compute_currency,
            'suggested_products': [],
            'valid_contract_amount': valid_contract_amount,
            'valid_product': valid_product,
            'active_contract': active_contract,
            'contains_contract': contains_contract,
            'subscription_accepted': subscription_accepted,
        }

        if order:
            _order = order
            if not request.env.context.get('pricelist'):
                _order = order.with_context(pricelist=order.pricelist_id.id)
            values['suggested_products'] = _order._cart_accessories()

        if post.get('type') == 'popover':
            return request.render("website_sale.cart_popover", values)

        if post.get('code_not_available'):
            values['code_not_available'] = post.get('code_not_available')

        return request.render("website_sale.cart", values)

    # fallback to "/shop/cart" if order not valid
    @http.route(['/shop/checkout'], type='http', auth="public", website=True)
    def checkout(self, **post):
        order = request.website.sale_get_order()
        valid_contract_amount = self._is_valid_contract_amount(order)
        valid_product = self._is_valid_products(order)
        active_contract = self._is_active_contract(order)
        subscription_accepted = order.mollie_incasso_accept

        if not subscription_accepted or not valid_contract_amount or not valid_product or active_contract:
            return request.redirect("/shop/cart")
        else:
            redirection = self.checkout_redirection(order)
            if redirection:
                return redirection

            if order.partner_id.id == request.website.user_id.sudo().partner_id.id:
                return request.redirect('/shop/address')

            for f in self._get_mandatory_billing_fields():
                if not order.partner_id[f]:
                    return request.redirect('/shop/address?partner_id=%d' % order.partner_id.id)

            values = self.checkout_values(**post)

            # Avoid useless rendering if called in ajax
            if post.get('xhr'):
                return 'ok'
            return request.render("website_sale.checkout", values)

    def _is_active_contract(self, order):
        contract_end_date = 'Unknown'
        contract_active = False
        current_date = datetime.datetime.strptime(fields.Date.today(), '%Y-%m-%d')
        contracts_found = request.env['account.analytic.account'].sudo().search([('recurring_invoices', '=', True),
                                                                                 ('partner_id', '=', order.partner_id.id)])
        for contract_found in contracts_found:
            if not contract_found.date_end:
                contract_end_date = datetime.datetime.strptime(fields.Date.today(), '%Y-%m-%d')
            else:
                contract_end_date = datetime.datetime.strptime(contract_found.date_end, '%Y-%m-%d')
            contract_active = current_date <= contract_end_date

        _logger.info('FIT Mollie: cart check active contract: %s, for contract end date: %s and today: %s', contract_active,
                     contract_end_date, current_date)
        return contract_active

    def _is_valid_contract_amount(self, order):
        is_valid_contract_amount = True
        if order:
            for order_line in order.order_line:
                for product_id in order_line.product_id:
                    if product_id.is_contract:
                        if order_line.product_uom_qty > 1:
                            is_valid_contract_amount = False

        _logger.info('FIT Mollie: cart check is valid contract amount = %s', is_valid_contract_amount)
        return is_valid_contract_amount

    def _is_valid_products(self, order):
        contains_contract = False
        contains_other = False
        if order:
            for order_line in order.order_line:
                for product_id in order_line.product_id:
                    if product_id.is_contract:
                        contains_contract = True
                    else:
                        contains_other = True

        _logger.info('FIT Mollie: cart check is valid product, contains contract: %s, contains other: %s', contains_contract, contains_other)
        if contains_contract and contains_other:
            return False
        return True

    def _contains_contract(self, order):
        contains_contract = False
        if order:
            for order_line in order.order_line:
                for product_id in order_line.product_id:
                    if product_id.is_contract:
                        contains_contract = True

        _logger.info('FIT Mollie: cart check, contains contract: %s', contains_contract)
        return contains_contract

    def _check_cart(self, order):
        contains_contract = False
        contains_contract_multiple = False
        contains_other = False
        if order:
            for order_line in order.order_line:
                for product_id in order_line.product_id:
                    if product_id.is_contract:
                        contains_contract = True
                        if order_line.product_uom_qty > 1:
                            contains_contract_multiple = True
                    else:
                        contains_other = True

        _logger.info('FIT Mollie: cart checkout found contract product: %s, multiple contract product: %s, and found other: %s',
                     contains_contract, contains_contract_multiple, contains_other)

        if contains_contract and contains_other:
            return False
        elif contains_contract and contains_contract_multiple:
            return False
        else:
            return True
