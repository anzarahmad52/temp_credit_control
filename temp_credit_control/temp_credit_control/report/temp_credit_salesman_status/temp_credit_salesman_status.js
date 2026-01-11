frappe.query_reports['Temp Credit Salesman Status'] = {
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
      fieldname: 'salesman_user',
      label: __('Salesman (User)'),
      fieldtype: 'Link',
      options: 'User',
      reqd: 0,
    },
    {
      fieldname: 'show_only_over_limit',
      label: __('Show Only Over Limit'),
      fieldtype: 'Check',
      default: 0,
    },
    {
      fieldname: 'show_blocked_only',
      label: __('Show Only Blocked'),
      fieldtype: 'Check',
      default: 0,
    },
    {
      fieldname: 'chart_mode',
      label: __('Chart Mode'),
      fieldtype: 'Select',
      options: 'Salesman Wise\nTop 10 Customers',
      default: 'Salesman Wise',
      reqd: 1,
    },
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (!data) return value;

    if (column.fieldname === 'remaining_limit' && flt(data.remaining_limit) < 0) {
      value = `<span style="color:#d9534f; font-weight:700">${value}</span>`;
    }

    if (column.fieldname === 'over_limit' && data.over_limit === 'Yes') {
      value = `<span style="color:#d9534f; font-weight:700">${value}</span>`;
    }

    if (column.fieldname === 'is_blocked' && data.is_blocked === 'Yes') {
      value = `<span style="color:#f0ad4e; font-weight:700">${value}</span>`;
    }

    if (column.fieldname === 'salesman_name' && data.salesman_name) {
      value = `<b>${frappe.utils.escape_html(data.salesman_name)}</b>`;
    }

    return value;
  },
};

function flt(v) {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
}
