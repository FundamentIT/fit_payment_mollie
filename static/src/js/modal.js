odoo.define('website_request_for_quotation.dialog', function (require) {
	'use strict';
	var ajax = require('web.ajax');

	$(document).ready(function(){
		$('#website_sale_order_mollie_incasso_accept').click(function(){
		    console.log('#website_sale_order_mollie_incasso_accept');
		    var sale_order_id = $("#website_sale_order_id").attr("value")
		    var is_accepted = $('#website_sale_order_mollie_incasso_accept')["0"].checked
		    console.log('#website_sale_order_mollie_incasso_accept order id: '+sale_order_id);
		    ajax.jsonRpc('/accept_mollie_incasso', 'call', {
		        'sale_order_id': sale_order_id,
		        'is_accepted': is_accepted,
		    }).then(function (deps) {
                console.log('#website_sale_order_mollie_incasso_accept successfully updated order '+sale_order_id);
            });
		});
	});
});
