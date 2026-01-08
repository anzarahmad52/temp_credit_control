frappe.ui.form.on('Temp Credit Settings', {
  refresh(frm) {
    frm.set_intro(
      __('This module enforces Temp Credit limits on <b>Sales Invoice</b> at server-side (hooks).'),
      'blue'
    );

    // Helpful default values if empty
    if (frm.is_new()) {
      frm.set_value('enabled', 1);
      frm.set_value('show_popup_on_allow', 1);
      frm.set_value('enable_warehouse_limit', 1);
      frm.set_value('enable_salesman_limit', 0);
      frm.set_value('default_customer_limit', frm.doc.default_customer_limit || 700);
      frm.set_value('default_max_unpaid_invoices', frm.doc.default_max_unpaid_invoices || 3);
      frm.set_value('default_warehouse_limit', frm.doc.default_warehouse_limit || 35000);
      frm.set_value('customer_tc_fieldname', frm.doc.customer_tc_fieldname || 'custom_payment_type');
      frm.set_value('temp_credit_value', frm.doc.temp_credit_value || 'Temp Credit');
    }
  }
});
