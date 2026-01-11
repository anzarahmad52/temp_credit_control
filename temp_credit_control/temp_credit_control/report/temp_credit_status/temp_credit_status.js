frappe.query_reports['Temp Credit Status'] = {
  filters: [
    {
      fieldname: 'company',
      label: __('Company'),
      fieldtype: 'Link',
      options: 'Company',
      reqd: 1,
      default: frappe.defaults.get_user_default('Company'),
    },
    {
      fieldname: 'duration',
      label: __('Duration'),
      fieldtype: 'Select',
      reqd: 1,
      default: 'Last 30 Days',
      options: ['Today', 'Last 30 Days', 'Last 60 Days', 'Last 90 Days', 'All'],
    },
    {
      fieldname: 'customer_group',
      label: __('Customer Group'),
      fieldtype: 'Link',
      options: 'Customer Group',
    },
    {
      fieldname: 'credit_type',
      label: __('Credit Type'),
      fieldtype: 'Select',
      // blank = All, "Temp Credit", "Credit"
      options: '\nTemp Credit\nCredit',
      default: '',
    },
    {
      fieldname: 'salesman_user',
      label: __('Salesman (User)'),
      fieldtype: 'Link',
      options: 'User',
      reqd: 0,
    },

    // ✅ Optional filters (useful for customer-wise view)
    {
      fieldname: 'customer',
      label: __('Customer'),
      fieldtype: 'Link',
      options: 'Customer',
      reqd: 0,
    },
    {
      fieldname: 'territory',
      label: __('Territory'),
      fieldtype: 'Link',
      options: 'Territory',
      reqd: 0,
    },

    {
      fieldname: 'summary_mode',
      label: __('Summary Mode'),
      fieldtype: 'Select',
      options: 'Salesman Wise\nCustomer Wise',
      default: 'Salesman Wise',
      reqd: 1,
    },

    // ✅ New checkbox
    {
      fieldname: 'show_only_over_limit',
      label: __('Show Only Over Limit'),
      fieldtype: 'Check',
      default: 0,
    },
  ],

  formatter: function (value, row, column, data, default_formatter) {
    // For HTML link column, return raw HTML (clickable)
    if (column.fieldname === 'open_invoices_link' && data && data.open_invoices_link) {
      return data.open_invoices_link;
    }

    value = default_formatter(value, row, column, data);
    if (!data) return value;

    // Highlight if used > limit
    if (column.fieldname === 'used_credit') {
      if (flt(data.used_credit) > flt(data.credit_limit)) {
        value = `<span style="color:#d9534f; font-weight:600">${value}</span>`;
      }
    }

    // Bold salesman name
    if (column.fieldname === 'salesman_name' && data.salesman_name) {
      value = `<b>${frappe.utils.escape_html(data.salesman_name)}</b>`;
    }

    // Color credit type
    if (column.fieldname === 'credit_type' && data.credit_type) {
      if (data.credit_type === 'Temp Credit') {
        value = `<span style="color:#f0ad4e; font-weight:600">${__('Temp Credit')}</span>`;
      } else {
        value = `<span style="color:#5cb85c; font-weight:600">${__('Credit')}</span>`;
      }
    }

    // Optional: highlight remaining_credit if negative (in case you add it later)
    if (column.fieldname === 'remaining_credit') {
      if (flt(data.remaining_credit) < 0) {
        value = `<span style="color:#d9534f; font-weight:600">${value}</span>`;
      }
    }

    return value;
  },
};

function flt(v) {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
}
