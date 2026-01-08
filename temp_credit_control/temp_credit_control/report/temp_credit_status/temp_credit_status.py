import json
import urllib.parse

import frappe
from frappe.utils import flt, add_days, nowdate, getdate


def execute(filters=None):
    filters = filters or {}

    # Full Temp Credit settings (field name + value + default limit)
    settings = _get_settings()

    columns = get_columns()
    data = get_data(filters, settings)

    # Manual Summary Mode:
    # - summary_mode = "Salesman Wise"  -> salesman-wise chart
    # - summary_mode = "Customer Wise" -> top customers chart
    chart = get_chart(data, filters)
    report_summary = get_report_summary(data)

    return columns, data, None, chart, report_summary


def get_columns():
    """Customer-wise credit view (like AR Summary, plus salesman)."""
    return [
        {
            "label": "Customer",
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 180,
        },
        {
            "label": "Customer Name",
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Customer Group",
            "fieldname": "customer_group",
            "fieldtype": "Link",
            "options": "Customer Group",
            "width": 160,
        },
        {
            "label": "Territory",
            "fieldname": "territory",
            "fieldtype": "Link",
            "options": "Territory",
            "width": 140,
        },
        {
            "label": "Credit Type",
            "fieldname": "credit_type",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": "Salesman Name",
            "fieldname": "salesman_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Salesman (User)",
            "fieldname": "salesman_user",
            "fieldtype": "Link",
            "options": "User",
            "width": 160,
        },
        {
            "label": "Credit Limit (SAR)",
            "fieldname": "credit_limit",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": "Used Credit (SAR)",
            "fieldname": "used_credit",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": "Remaining Limit (SAR)",
            "fieldname": "remaining_credit",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "label": "Open Sales Invoices",
            "fieldname": "open_invoices_link",
            "fieldtype": "HTML",
            "width": 160,
        },
    ]


def get_data(filters, settings):
    company = (filters.get("company") or "").strip()
    duration = (filters.get("duration") or "Last 30 Days").strip()
    customer_group = (filters.get("customer_group") or "").strip()
    credit_type_filter = (filters.get("credit_type") or "").strip()  # '', 'Temp Credit', 'Credit'
    salesman_user_filter = (filters.get("salesman_user") or "").strip()

    if not company:
        return []

    # 1) Credit limits per customer (for normal credit customers)
    credit_limits = _get_standard_credit_limits(company, customer_group)

    # 2) Outstanding per customer from Sales Invoice (only unpaid invoices)
    #    includes optional salesman_user filter (si.owner)
    outstanding_map = _get_outstanding_summary(
        company=company,
        duration=duration,
        customer_group=customer_group,
        salesman_user=salesman_user_filter,
    )

    # Base set = customers with unpaid invoices (for both Credit & Temp Credit)
    customers_set = set(outstanding_map.keys())
    if not customers_set:
        return []

    customers_list = list(customers_set)

    # 3) Temp credit flags & per-customer temp policy (limit override)
    temp_flags = _get_temp_customer_flags(customers_list, settings)
    temp_policies = _get_policies_for_customers(customers_list)

    # 4) Customer master
    customers = frappe.get_all(
        "Customer",
        filters={"name": ["in", customers_list]},
        fields=["name", "customer_name", "customer_group", "territory"],
        order_by="customer_name asc",
        limit_page_length=100000,
    )

    data = []
    for c in customers:
        is_temp = 1 if temp_flags.get(c.name) else 0
        credit_type = "Temp Credit" if is_temp else "Credit"

        # Credit Type filter
        if credit_type_filter == "Temp Credit" and not is_temp:
            continue
        if credit_type_filter == "Credit" and is_temp:
            continue

        # Compute Credit Limit
        if is_temp:
            # Temp Credit limit from policy or default setting
            pol = temp_policies.get(c.name) or {}
            credit_limit = _effective_flt(
                pol.get("credit_limit_override"),
                settings["default_customer_limit"],
            )
        else:
            # Normal credit limit from Customer Credit Limit
            credit_limit = flt(credit_limits.get(c.name) or 0)

        # For "Credit" filter we also require a positive credit limit
        if credit_type_filter == "Credit" and credit_limit <= 0:
            continue

        summary = outstanding_map.get(c.name) or {}
        used_credit = flt(summary.get("outstanding_sum") or 0)
        remaining = credit_limit - used_credit

        salesman_user = (summary.get("salesman_user") or "").strip()
        salesman_name = (summary.get("salesman_name") or "").strip()
        if not salesman_name:
            salesman_name = salesman_user or ""

        # Build "Open Sales Invoices" link
        open_inv_url = _build_unpaid_invoices_list_url(c.name)

        data.append(
            {
                "customer": c.name,
                "customer_name": c.customer_name,
                "customer_group": c.customer_group,
                "territory": c.territory,
                "credit_type": credit_type,
                "salesman_user": salesman_user,
                "salesman_name": salesman_name,
                "credit_limit": credit_limit,
                "used_credit": used_credit,
                "remaining_credit": remaining,
                "open_invoices_link": f'<a href="{open_inv_url}" target="_blank">Open</a>',
            }
        )

    return data


# ---------------- Charts & Summary ----------------


def get_chart(data, filters=None):
    """
    Manual Summary Mode:

    - summary_mode = "Salesman Wise"
        -> Salesman-wise chart (top 10 salesmen by used credit).
    - summary_mode = "Customer Wise"
        -> Top 10 high-used-credit customers (within filters).
    """
    if not data:
        return None

    filters = filters or {}
    summary_mode = (filters.get("summary_mode") or "Salesman Wise").strip()

    if summary_mode == "Customer Wise":
        return _chart_top_customers(data)

    # Default: Salesman Wise
    return _chart_salesman_wise(data)


def _chart_salesman_wise(data):
    """
    Salesman-wise chart:
    - X-axis: Salesman
    - Dataset: Used Credit, Credit Limit (sum of customers)
    - Only top 10 by Used Credit
    """
    agg = {}

    for d in data:
        key = (d.get("salesman_name") or d.get("salesman_user") or "Not Set").strip()
        if key not in agg:
            agg[key] = {
                "used_credit": 0.0,
                "credit_limit": 0.0,
            }

        agg[key]["used_credit"] += flt(d.get("used_credit"))
        agg[key]["credit_limit"] += flt(d.get("credit_limit"))

    # Convert to list and sort by used_credit desc
    rows = [
        {
            "salesman": name,
            "used_credit": vals["used_credit"],
            "credit_limit": vals["credit_limit"],
        }
        for name, vals in agg.items()
    ]
    rows.sort(key=lambda x: flt(x["used_credit"]), reverse=True)

    # Take top 10
    top = rows[:10]

    if not top:
        return None

    labels = [r["salesman"] for r in top]
    used_values = [round(flt(r["used_credit"]), 2) for r in top]
    limit_values = [round(flt(r["credit_limit"]), 2) for r in top]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Used Credit (SAR)", "values": used_values},
                {"name": "Credit Limit (SAR)", "values": limit_values},
            ],
        },
        "type": "bar",
        "height": 300,
        "colors": None,
    }


def _chart_top_customers(data):
    """
    Top 10 high-used-credit customers (within current filter context).
    - X-axis: Customer
    - Dataset: Used Credit & Credit Limit
    """
    sorted_rows = sorted(
        data,
        key=lambda d: flt(d.get("used_credit")),
        reverse=True,
    )
    top = sorted_rows[:10]

    if not top:
        return None

    labels = [d["customer"] for d in top]
    used_values = [round(flt(d.get("used_credit")), 2) for d in top]
    limit_values = [round(flt(d.get("credit_limit")), 2) for d in top]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Used Credit (SAR)", "values": used_values},
                {"name": "Credit Limit (SAR)", "values": limit_values},
            ],
        },
        "type": "bar",
        "height": 300,
        "colors": None,
    }


def get_report_summary(data):
    total_used = 0.0
    total_limit = 0.0
    total_remaining = 0.0

    for r in data:
        used = flt(r.get("used_credit"))
        limit_ = flt(r.get("credit_limit"))
        total_used += used
        total_limit += limit_
        total_remaining += (limit_ - used)

    return [
        {
            "label": "Total Used Credit",
            "value": round(total_used, 2),
            "indicator": "Orange",
        },
        {
            "label": "Total Credit Limit",
            "value": round(total_limit, 2),
            "indicator": "Blue",
        },
        {
            "label": "Total Remaining Limit",
            "value": round(total_remaining, 2),
            "indicator": "Green",
        },
    ]


# ---------------- Duration helper ----------------


def get_date_limit(duration):
    """
    Convert duration string to a posting_date lower bound.
    - Today         -> today
    - Last 30 Days  -> today - 30
    - Last 60 Days  -> today - 60
    - Last 90 Days  -> today - 90
    - All           -> None (no date filter)
    """
    today = getdate(nowdate())

    if duration == "Today":
        return today
    if duration == "Last 30 Days":
        return add_days(today, -30)
    if duration == "Last 60 Days":
        return add_days(today, -60)
    if duration == "Last 90 Days":
        return add_days(today, -90)

    return None  # All


# ---------------- SQL Helpers ----------------


def _get_standard_credit_limits(company, customer_group=None):
    """
    Standard credit limit from Customer Credit Limit.
    We include:
      - rows where company matches
      - rows where company is blank (global limit)
    """
    where_extra = ""
    params = {"company": company}

    if customer_group:
        where_extra = "AND c.customer_group = %(customer_group)s"
        params["customer_group"] = customer_group

    rows = frappe.db.sql(
        f"""
        SELECT
            ccl.parent AS customer,
            MAX(ccl.credit_limit) AS credit_limit
        FROM `tabCustomer Credit Limit` ccl
        INNER JOIN `tabCustomer` c ON c.name = ccl.parent
        WHERE
            (IFNULL(ccl.company, '') = '' OR ccl.company = %(company)s)
            {where_extra}
        GROUP BY ccl.parent
        """,
        params,
        as_dict=True,
    )

    limits = {}
    for r in rows:
        limits[r.customer] = flt(r.credit_limit)

    return limits


def _get_outstanding_summary(company, duration, customer_group=None, salesman_user=None):
    """
    Open sales invoices only, grouped per customer.
    Also returns latest invoice owner as salesman.

    If salesman_user is given, only invoices where si.owner = salesman_user
    will be included.
    """
    result = {}

    date_limit = get_date_limit(duration)
    date_condition = ""
    extra_join = ""
    extra_where = ""
    salesman_condition = ""
    params = {"company": company}

    if date_limit:
        date_condition = "AND si.posting_date >= %(date_limit)s"
        params["date_limit"] = date_limit

    if customer_group:
        extra_join = "LEFT JOIN `tabCustomer` c ON c.name = si.customer"
        extra_where = "AND c.customer_group = %(customer_group)s"
        params["customer_group"] = customer_group

    if salesman_user:
        salesman_condition = "AND si.owner = %(salesman_user)s"
        params["salesman_user"] = salesman_user

    rows = frappe.db.sql(
        f"""
        WITH inv_base AS (
            SELECT
                si.name AS invoice,
                si.customer AS customer,
                si.owner AS owner,
                si.modified AS modified,
                si.outstanding_amount AS outstanding_amount
            FROM `tabSales Invoice` si
            {extra_join}
            WHERE
                si.docstatus = 1
                AND IFNULL(si.is_return, 0) = 0
                AND IFNULL(si.outstanding_amount, 0) > 0
                AND si.company = %(company)s
                {date_condition}
                {extra_where}
                {salesman_condition}
        ),
        agg AS (
            SELECT
                customer,
                COUNT(invoice) AS invoice_count,
                SUM(outstanding_amount) AS outstanding_sum
            FROM inv_base
            GROUP BY customer
        ),
        latest AS (
            SELECT
                b.customer,
                b.owner,
                u.full_name
            FROM inv_base b
            LEFT JOIN `tabUser` u ON u.name = b.owner
            INNER JOIN (
                SELECT customer, MAX(modified) AS mx
                FROM inv_base
                GROUP BY customer
            ) x ON x.customer = b.customer AND x.mx = b.modified
        )
        SELECT
            a.customer,
            a.invoice_count,
            a.outstanding_sum,
            l.owner AS salesman_user,
            l.full_name AS salesman_name
        FROM agg a
        LEFT JOIN latest l ON l.customer = a.customer
        """,
        params,
        as_dict=True,
    )

    for r in rows:
        result[r.customer] = {
            "invoice_count": int(r.invoice_count or 0),
            "outstanding_sum": flt(r.outstanding_sum),
            "salesman_user": (r.salesman_user or "").strip(),
            "salesman_name": (r.salesman_name or "").strip(),
        }

    return result


# ---------------- Temp Credit Helpers ----------------


def _get_settings():
    """
    Read Temp Credit Settings:
    - customer_tc_fieldname (e.g. custom_payment_type)
    - temp_credit_value (e.g. Temp Credit)
    - default_customer_limit (for temp credit)
    """
    try:
        s = frappe.get_single("Temp Credit Settings")
    except Exception:
        return {
            "customer_tc_fieldname": "custom_payment_type",
            "temp_credit_value": "__NO_TEMP_VALUE__",
            "default_customer_limit": 0,
        }

    customer_tc_fieldname = (
        getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type"
    ).strip()
    temp_credit_value = (
        getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit"
    ).strip()

    return {
        "customer_tc_fieldname": customer_tc_fieldname,
        "temp_credit_value": temp_credit_value,
        "default_customer_limit": flt(getattr(s, "default_customer_limit", 0)),
    }


def _get_temp_customer_flags(customer_names, settings):
    """
    Return dict {customer_name: 1} for customers marked as Temp Credit
    using field+value from Temp Credit Settings.
    """
    flags = {}
    if not customer_names:
        return flags

    tc_field = settings["customer_tc_fieldname"]
    tc_value = settings["temp_credit_value"]

    rows = frappe.get_all(
        "Customer",
        filters={
            "name": ["in", customer_names],
            tc_field: tc_value,
        },
        fields=["name"],
        limit_page_length=100000,
    )

    for r in rows:
        flags[r.name] = 1

    return flags


def _get_policies_for_customers(customer_names):
    """
    Temp Credit Customer Policy per customer (for limit override).
    """
    policies = {}
    if not customer_names:
        return policies

    rows = frappe.get_all(
        "Temp Credit Customer Policy",
        filters={"customer": ["in", customer_names]},
        fields=["customer", "enabled", "credit_limit_override"],
        limit_page_length=100000,
    )

    for r in rows:
        if flt(r.get("enabled", 1)) == 0:
            continue
        policies[r.customer] = r

    return policies


def _effective_flt(override_value, default_value):
    ov = flt(override_value)
    return ov if ov > 0 else flt(default_value)


def _build_unpaid_invoices_list_url(customer):
    """Clickable link to open all unpaid Sales Invoices for this customer."""
    filters = [
        ["Sales Invoice", "customer", "=", customer],
        ["Sales Invoice", "docstatus", "=", 1],
        ["Sales Invoice", "is_return", "=", 0],
        ["Sales Invoice", "outstanding_amount", ">", 0],
    ]
    filters_enc = urllib.parse.quote(json.dumps(filters))
    return f"/app/sales-invoice?filters={filters_enc}"
