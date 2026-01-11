/* temp_credit_status.js */

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
    {
      fieldname: 'show_only_over_limit',
      label: __('Show Only Over Limit'),
      fieldtype: 'Check',
      default: 0,
    },
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (!data) return value;

    const used = flt(data.customer_used_credit);
    const limit = flt(data.credit_limit);
    const remaining = flt(data.remaining_credit);

    // ✅ Invoice Outstanding red if customer is over limit (used > limit)
    if (column.fieldname === 'invoice_outstanding') {
      if (limit > 0 && used > limit) {
        value = `<span style="color:#d9534f; font-weight:600">${value}</span>`;
      }
    }

    // ✅ Remaining Limit red if negative
    if (column.fieldname === 'remaining_credit') {
      if (remaining < 0) {
        value = `<span style="color:#d9534f; font-weight:600">${value}</span>`;
      }
    }

    // ✅ Also highlight customer_used_credit if over limit
    if (column.fieldname === 'customer_used_credit') {
      if (limit > 0 && used > limit) {
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

    return value;
  },
};

function flt(v) {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
}
