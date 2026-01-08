frappe.ui.form.on('Temp Credit Salesman Policy', {
  refresh(frm) {
    frm.set_intro(
      __('Use this to set/override Temp Credit outstanding limit per salesman (User).'),
      'orange'
    );

    // Quick button: open User
    if (frm.doc.user) {
      frm.add_custom_button(__('Open User'), () => {
        frappe.set_route('Form', 'User', frm.doc.user);
      });
    }

    frm.toggle_display('block_reason', !!frm.doc.is_blocked);
  },

  is_blocked(frm) {
    frm.toggle_display('block_reason', !!frm.doc.is_blocked);

    if (frm.doc.is_blocked && !frm.doc.block_reason) {
      frappe.msgprint(__('Please add Block Reason.'), __('Missing Reason'));
    }
  },

  validate(frm) {
    if (frm.doc.max_outstanding_limit && frm.doc.max_outstanding_limit < 0) {
      frappe.throw(__('Max Outstanding Limit cannot be negative.'));
    }
  }
});
