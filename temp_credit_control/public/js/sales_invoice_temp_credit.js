(() => {
  const DOCTYPE = 'Sales Invoice';

  async function getSettings() {
    // Single DocType: name is always "Temp Credit Settings"
    const r = await frappe.db.get_doc('Temp Credit Settings', 'Temp Credit Settings');
    return r || {};
  }

  async function getCustomerPolicy(customer) {
    if (!customer) return null;

    const r = await frappe.db.get_value(
      'Temp Credit Customer Policy',
      { customer },
      ['enabled', 'credit_limit_override', 'max_unpaid_invoices_override', 'is_blacklisted', 'blacklist_reason']
    );

    return (r && r.message) ? r.message : null;
  }

  async function getOutstandingForCustomer(customer) {
    if (!customer) return { count: 0, total: 0 };

    // Count + SUM outstanding_amount for submitted unpaid invoices
    const r = await frappe.call({
      method: 'frappe.client.get_list',
      args: {
        doctype: 'Sales Invoice',
        fields: ['name', 'outstanding_amount'],
        filters: {
          customer: customer,
          docstatus: 1,
          is_return: 0,
          outstanding_amount: ['>', 0]
        },
        limit_page_length: 500
      }
    });

    const rows = (r.message || []);
    let count = 0;
    let total = 0;

    for (const row of rows) {
      count += 1;
      total += flt(row.outstanding_amount);
    }

    return { count, total };
  }

  function flt(v) {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
  }

  function isTempCreditCustomer(customer_tc_value, customer_payment_type) {
    return (customer_payment_type || '').trim() === (customer_tc_value || 'Temp Credit').trim();
  }

  async function getCustomerPaymentType(customer, tc_fieldname) {
    if (!customer) return '';

    const r = await frappe.db.get_value('Customer', customer, tc_fieldname || 'custom_payment_type');
    return (r && r.message) ? (r.message[tc_fieldname || 'custom_payment_type'] || '') : '';
  }

  function setIndicator(frm, title, color = 'blue') {
    // ERPNext indicator colors: green, orange, red, blue
    frm.dashboard.set_headline(`<div class="small">${title}</div>`);
    frm.dashboard.set_headline_alert(title, color);
  }

  function clearIndicator(frm) {
    frm.dashboard.clear_headline();
    frm.dashboard.clear_headline_alert();
  }

  async function showTempCreditInfo(frm) {
    try {
      if (frm.doc.docstatus === 2) {
        clearIndicator(frm);
        return;
      }

      const customer = frm.doc.customer;
      if (!customer) {
        clearIndicator(frm);
        return;
      }

      const settings = await getSettings();
      if (!flt(settings.enabled)) {
        clearIndicator(frm);
        return;
      }

      const tc_fieldname = settings.customer_tc_fieldname || 'custom_payment_type';
      const tc_value = settings.temp_credit_value || 'Temp Credit';

      const payment_type = await getCustomerPaymentType(customer, tc_fieldname);

      if (!isTempCreditCustomer(tc_value, payment_type)) {
        clearIndicator(frm);
        return;
      }

      // Customer policy
      const policy = await getCustomerPolicy(customer);

      if (policy && flt(policy.enabled) === 0) {
        clearIndicator(frm);
        return;
      }

      if (policy && flt(policy.is_blacklisted) === 1) {
        const reason = (policy.blacklist_reason || '').trim() || 'Customer is blacklisted for Temp Credit.';
        setIndicator(frm, `❌ Temp Credit: BLACKLISTED — ${reason}`, 'red');
        frappe.show_alert({ message: `Temp Credit blocked: ${reason}`, indicator: 'red' });
        return;
      }

      // Effective limits
      let max_credit = flt(policy && policy.credit_limit_override) || flt(settings.default_customer_limit) || 700;
      let max_invoices = parseInt((policy && policy.max_unpaid_invoices_override) || settings.default_max_unpaid_invoices || 3, 10);
      if (isNaN(max_invoices) || max_invoices < 0) max_invoices = 3;

      // Used credit (submitted outstanding)
      const used = await getOutstandingForCustomer(customer);
      let invoice_count = used.count;
      let total_outstanding = used.total;

      // Include current invoice (draft / editing)
      const current_amount = flt(frm.doc.grand_total);
      if (frm.doc.docstatus === 0) {
        invoice_count += 1;
        total_outstanding += current_amount;
      }

      const remaining_credit = max_credit - total_outstanding;
      const remaining_invoices = max_invoices - invoice_count;

      const msg =
        `🧾 Temp Credit Info — ${customer}<br>` +
        `• Limit: <b>${max_credit.toFixed(2)}</b> SAR<br>` +
        `• Current Invoice: <b>${current_amount.toFixed(2)}</b> SAR<br>` +
        `• Unpaid Invoices (incl. this): <b>${invoice_count}</b> / ${max_invoices}<br>` +
        `• Outstanding (incl. this): <b>${total_outstanding.toFixed(2)}</b> SAR<br>` +
        `• Remaining Credit: <b>${Math.max(remaining_credit, 0).toFixed(2)}</b> SAR<br>` +
        `• Remaining Invoices: <b>${Math.max(remaining_invoices, 0)}</b>`;

      const exceeded = (invoice_count > max_invoices) || (total_outstanding > max_credit);

      if (exceeded) {
        setIndicator(frm, '❌ Temp Credit will exceed limits (server will block on submit).', 'red');
        frappe.msgprint({
          title: '❌ Temp Credit Warning',
          indicator: 'red',
          message: msg
        });
      } else {
        setIndicator(frm, '✅ Temp Credit within limits.', 'green');
        if (flt(settings.show_popup_on_allow)) {
          frappe.show_alert({ message: 'Temp Credit within limits', indicator: 'green' });
        }
      }
    } catch (e) {
      // Don’t break Sales Invoice UI
      console.error('[Temp Credit JS]', e);
    }
  }

  frappe.ui.form.on(DOCTYPE, {
    refresh(frm) {
      // run once on refresh
      showTempCreditInfo(frm);
    },

    customer(frm) {
      showTempCreditInfo(frm);
    },

    // when totals change, re-check
    grand_total(frm) {
      showTempCreditInfo(frm);
    },

    // if warehouse changes (if you later add warehouse UI check)
    set_warehouse(frm) {
      showTempCreditInfo(frm);
    }
  });
})();
