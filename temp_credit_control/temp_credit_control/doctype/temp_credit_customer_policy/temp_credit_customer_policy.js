frappe.ui.form.on('Temp Credit Customer Policy', {
  refresh(frm) {
    frm.set_intro(
      __('Use this to override Temp Credit limits per customer or blacklist them.'),
      'green'
    );

    // Quick button: open Customer
    if (frm.doc.customer) {
      frm.add_custom_button(__('Open Customer'), () => {
        frappe.set_route('Form', 'Customer', frm.doc.customer);
      });
    }

    // show/hide reason fields handled by depends_on too, but keep UI clean
    frm.toggle_display('blacklist_reason', !!frm.doc.is_blacklisted);
  },

  is_blacklisted(frm) {
    frm.toggle_display('blacklist_reason', !!frm.doc.is_blacklisted);

    if (frm.doc.is_blacklisted && !frm.doc.blacklist_reason) {
      frappe.msgprint(__('Please add Blacklist Reason.'), __('Missing Reason'));
    }
  },

  validate(frm) {
    // basic checks
    if (frm.doc.credit_limit_override && frm.doc.credit_limit_override < 0) {
      frappe.throw(__('Credit Limit Override cannot be negative.'));
    }
    if (frm.doc.max_unpaid_invoices_override && frm.doc.max_unpaid_invoices_override < 0) {
      frappe.throw(__('Max Unpaid Invoices Override cannot be negative.'));
    }
  }
});
