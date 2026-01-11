import frappe
from frappe.utils import flt, add_days, nowdate, getdate


def execute(filters=None):
    filters = filters or {}

    settings = _get_settings()

    columns = get_columns()
    data, customer_summary = get_data(filters, settings)

    chart = get_chart(customer_summary, data, filters)
    report_summary = get_report_summary(customer_summary)

    return columns, data, None, chart, report_summary


def get_columns():
    """Invoice-wise unpaid invoices with customer-level limits & totals."""
    return [
        {
            "label": "Sales Invoice",
            "fieldname": "sales_invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 160,
        },
        {
            "label": "Posting Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Invoice Outstanding (SAR)",
            "fieldname": "invoice_outstanding",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "label": "Customer",
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
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
            "width": 150,
        },
        {
            "label": "Territory",
            "fieldname": "territory",
            "fieldtype": "Link",
            "options": "Territory",
            "width": 130,
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
            "width": 170,
        },
        {
            "label": "Credit Limit (SAR)",
            "fieldname": "credit_limit",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": "Customer Used Credit (SAR)",
            "fieldname": "customer_used_credit",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": "Remaining Limit (SAR)",
            "fieldname": "remaining_credit",
            "fieldtype": "Currency",
            "width": 160,
        },
    ]


def get_data(filters, settings):
    company = (filters.get("company") or "").strip()
    duration = (filters.get("duration") or "Last 30 Days").strip()
    customer_group = (filters.get("customer_group") or "").strip()
    credit_type_filter = (filters.get("credit_type") or "").strip()  # '', 'Temp Credit', 'Credit'
    salesman_user_filter = (filters.get("salesman_user") or "").strip()
    customer_filter = (filters.get("customer") or "").strip()
    territory_filter = (filters.get("territory") or "").strip()
    show_only_over_limit = int(filters.get("show_only_over_limit") or 0)

    if not company:
        return [], {}

    # 1) Pull ALL unpaid invoices (invoice-wise)
    invoices = _get_unpaid_invoices(
        company=company,
        duration=duration,
        customer_group=customer_group,
        salesman_user=salesman_user_filter,
        customer=customer_filter,
        territory=territory_filter,
    )
    if not invoices:
        return [], {}

    customers_list = list({d["customer"] for d in invoices if d.get("customer")})
    if not customers_list:
        return [], {}

    # 2) Customer master data
    customers_map = _get_customers_map(customers_list)

    # 3) Standard credit limits (for normal credit customers)
    credit_limits = _get_standard_credit_limits(company, customer_group)

    # 4) Temp credit flags & policies
    temp_flags = _get_temp_customer_flags(customers_list, settings)
    temp_policies = _get_policies_for_customers(customers_list)

    # 5) Customer outstanding totals (customer-wise) from the invoice list itself
    #    (this avoids extra SQL and matches the exact invoice set / filters)
    customer_outstanding = {}
    for inv in invoices:
        cust = inv["customer"]
        customer_outstanding[cust] = flt(customer_outstanding.get(cust) or 0) + flt(inv.get("outstanding_amount") or 0)

    # 6) Build rows (invoice-wise), but show customer limit/used/remaining repeated
    out = []
    customer_summary = {}  # for chart + summary (distinct customers)

    for inv in invoices:
        cust = inv["customer"]
        cdoc = customers_map.get(cust)
        if not cdoc:
            continue

        is_temp = 1 if temp_flags.get(cust) else 0
        credit_type = "Temp Credit" if is_temp else "Credit"

        # Credit type filter
        if credit_type_filter == "Temp Credit" and not is_temp:
            continue
        if credit_type_filter == "Credit" and is_temp:
            continue

        # Credit limit
        if is_temp:
            pol = temp_policies.get(cust) or {}
            credit_limit = _effective_flt(pol.get("credit_limit_override"), settings["default_customer_limit"])
        else:
            credit_limit = flt(credit_limits.get(cust) or 0)

        # For "Credit" filter we also require positive credit limit
        if credit_type_filter == "Credit" and credit_limit <= 0:
            continue

        cust_used = flt(customer_outstanding.get(cust) or 0)
        remaining = credit_limit - cust_used

        # Over-limit filter
        if show_only_over_limit and credit_limit > 0 and cust_used <= credit_limit:
            continue
        if show_only_over_limit and credit_limit <= 0:
            # If credit limit not defined, don't show in over-limit mode
            continue

        salesman_user = (inv.get("owner") or "").strip()
        salesman_name = (inv.get("salesman_name") or "").strip() or salesman_user

        out.append(
            {
                "sales_invoice": inv["name"],
                "posting_date": inv.get("posting_date"),
                "invoice_outstanding": flt(inv.get("outstanding_amount") or 0),
                "customer": cust,
                "customer_name": cdoc.get("customer_name"),
                "customer_group": cdoc.get("customer_group"),
                "territory": cdoc.get("territory"),
                "credit_type": credit_type,
                "salesman_user": salesman_user,
                "salesman_name": salesman_name,
                "credit_limit": credit_limit,
                "customer_used_credit": cust_used,
                "remaining_credit": remaining,
            }
        )

        # Summary store by customer (distinct)
        if cust not in customer_summary:
            customer_summary[cust] = {
                "customer": cust,
                "customer_name": cdoc.get("customer_name"),
                "salesman_user": salesman_user,
                "salesman_name": salesman_name,
                "credit_limit": flt(credit_limit),
                "used_credit": flt(cust_used),
            }

    # Sort by posting date desc, then invoice
    out.sort(key=lambda x: (x.get("posting_date") or "", x.get("sales_invoice") or ""), reverse=True)

    return out, customer_summary


# ---------------- Charts & Summary ----------------

def get_chart(customer_summary, invoice_rows, filters=None):
    """
    Manual Summary Mode:
      - "Salesman Wise": top 10 salesmen by TOTAL invoice outstanding (within filters)
      - "Customer Wise": top 10 customers by USED credit (customer outstanding)
    """
    if not invoice_rows:
        return None

    filters = filters or {}
    summary_mode = (filters.get("summary_mode") or "Salesman Wise").strip()

    if summary_mode == "Customer Wise":
        return _chart_top_customers(customer_summary)

    return _chart_salesman_wise(invoice_rows, customer_summary)


def _chart_salesman_wise(invoice_rows, customer_summary):
    # Used = sum of invoice outstanding per salesman
    used_by_salesman = {}
    # Limit = sum of DISTINCT customer credit limits per salesman (avoid invoice duplication)
    custs_by_salesman = {}

    for r in invoice_rows:
        s_key = (r.get("salesman_name") or r.get("salesman_user") or "Not Set").strip()
        used_by_salesman[s_key] = flt(used_by_salesman.get(s_key) or 0) + flt(r.get("invoice_outstanding") or 0)

    for cust, csum in (customer_summary or {}).items():
        s_key = (csum.get("salesman_name") or csum.get("salesman_user") or "Not Set").strip()
        if s_key not in custs_by_salesman:
            custs_by_salesman[s_key] = set()
        custs_by_salesman[s_key].add(cust)

    limit_by_salesman = {}
    for s_key, cust_set in custs_by_salesman.items():
        total = 0.0
        for cust in cust_set:
            total += flt((customer_summary.get(cust) or {}).get("credit_limit") or 0)
        limit_by_salesman[s_key] = total

    rows = []
    for s_key, used in used_by_salesman.items():
        rows.append(
            {
                "salesman": s_key,
                "used": flt(used),
                "limit": flt(limit_by_salesman.get(s_key) or 0),
            }
        )

    rows.sort(key=lambda x: flt(x["used"]), reverse=True)
    top = rows[:10]
    if not top:
        return None

    return {
        "data": {
            "labels": [r["salesman"] for r in top],
            "datasets": [
                {"name": "Used Credit (SAR)", "values": [round(flt(r["used"]), 2) for r in top]},
                {"name": "Credit Limit (SAR)", "values": [round(flt(r["limit"]), 2) for r in top]},
            ],
        },
        "type": "bar",
        "height": 300,
        "colors": None,
    }


def _chart_top_customers(customer_summary):
    rows = list(customer_summary.values()) if customer_summary else []
    if not rows:
        return None

    rows.sort(key=lambda d: flt(d.get("used_credit")), reverse=True)
    top = rows[:10]
    if not top:
        return None

    return {
        "data": {
            "labels": [d.get("customer") for d in top],
            "datasets": [
                {"name": "Used Credit (SAR)", "values": [round(flt(d.get("used_credit")), 2) for d in top]},
                {"name": "Credit Limit (SAR)", "values": [round(flt(d.get("credit_limit")), 2) for d in top]},
            ],
        },
        "type": "bar",
        "height": 300,
        "colors": None,
    }


def get_report_summary(customer_summary):
    """
    Summary must be customer-distinct (not invoice rows), otherwise totals duplicate.
    """
    total_used = 0.0
    total_limit = 0.0
    total_remaining = 0.0

    for _, r in (customer_summary or {}).items():
        used = flt(r.get("used_credit"))
        limit_ = flt(r.get("credit_limit"))
        total_used += used
        total_limit += limit_
        total_remaining += (limit_ - used)

    return [
        {"label": "Total Used Credit", "value": round(total_used, 2), "indicator": "Orange"},
        {"label": "Total Credit Limit", "value": round(total_limit, 2), "indicator": "Blue"},
        {"label": "Total Remaining Limit", "value": round(total_remaining, 2), "indicator": "Green"},
    ]


# ---------------- Duration helper ----------------

def get_date_limit(duration):
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

def _get_unpaid_invoices(company, duration, customer_group=None, salesman_user=None, customer=None, territory=None):
    """
    Returns ALL unpaid invoices (invoice-wise) with basic info + salesman name.
    Filters:
      - company (required)
      - posting_date by duration
      - customer_group, territory via Customer join
      - salesman_user (invoice owner)
      - customer exact
    """
    date_limit = get_date_limit(duration)

    params = {"company": company}
    cond = ["si.docstatus = 1", "IFNULL(si.is_return,0) = 0", "IFNULL(si.outstanding_amount,0) > 0", "si.company = %(company)s"]

    joins = "LEFT JOIN `tabUser` u ON u.name = si.owner"
    cjoin = ""
    ccond = []

    if date_limit:
        cond.append("si.posting_date >= %(date_limit)s")
        params["date_limit"] = date_limit

    if salesman_user:
        cond.append("si.owner = %(salesman_user)s")
        params["salesman_user"] = salesman_user

    if customer:
        cond.append("si.customer = %(customer)s")
        params["customer"] = customer

    # Only join Customer table if needed
    if customer_group or territory:
        cjoin = "LEFT JOIN `tabCustomer` c ON c.name = si.customer"
        if customer_group:
            ccond.append("c.customer_group = %(customer_group)s")
            params["customer_group"] = customer_group
        if territory:
            ccond.append("c.territory = %(territory)s")
            params["territory"] = territory

    where_sql = " AND ".join(cond)
    if ccond:
        where_sql += " AND " + " AND ".join(ccond)

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer,
            si.posting_date,
            si.outstanding_amount,
            si.owner,
            u.full_name AS salesman_name
        FROM `tabSales Invoice` si
        {joins}
        {cjoin}
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.modified DESC
        """,
        params,
        as_dict=True,
    )

    return rows or []


def _get_customers_map(customer_names):
    if not customer_names:
        return {}

    rows = frappe.get_all(
        "Customer",
        filters={"name": ["in", customer_names]},
        fields=["name", "customer_name", "customer_group", "territory"],
        limit_page_length=100000,
    )

    return {r["name"]: r for r in rows}


def _get_standard_credit_limits(company, customer_group=None):
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


# ---------------- Temp Credit Helpers ----------------

def _get_settings():
    try:
        s = frappe.get_single("Temp Credit Settings")
    except Exception:
        return {
            "customer_tc_fieldname": "custom_payment_type",
            "temp_credit_value": "__NO_TEMP_VALUE__",
            "default_customer_limit": 0,
        }

    customer_tc_fieldname = (getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type").strip()
    temp_credit_value = (getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit").strip()

    return {
        "customer_tc_fieldname": customer_tc_fieldname,
        "temp_credit_value": temp_credit_value,
        "default_customer_limit": flt(getattr(s, "default_customer_limit", 0)),
    }


def _get_temp_customer_flags(customer_names, settings):
    flags = {}
    if not customer_names:
        return flags

    tc_field = settings["customer_tc_fieldname"]
    tc_value = settings["temp_credit_value"]

    rows = frappe.get_all(
        "Customer",
        filters={"name": ["in", customer_names], tc_field: tc_value},
        fields=["name"],
        limit_page_length=100000,
    )

    for r in rows:
        flags[r.name] = 1

    return flags


def _get_policies_for_customers(customer_names):
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






# import frappe
# from frappe.utils import flt, add_days, nowdate, getdate


# def execute(filters=None):
#     filters = filters or {}

#     settings = _get_settings()

#     columns = get_columns()
#     data = get_data(filters, settings)

#     chart = get_chart(data, filters)
#     report_summary = get_report_summary(data)

#     return columns, data, None, chart, report_summary


# def get_columns():
#     """
#     Invoice-wise rows (ALL unpaid invoices).
#     Keeps customer-level credit limit & remaining repeated per invoice.
#     """
#     return [
#         {
#             "label": "Sales Invoice",
#             "fieldname": "sales_invoice",
#             "fieldtype": "Link",
#             "options": "Sales Invoice",
#             "width": 160,
#         },
#         {
#             "label": "Posting Date",
#             "fieldname": "posting_date",
#             "fieldtype": "Date",
#             "width": 110,
#         },
#         {
#             "label": "Grand Total (SAR)",
#             "fieldname": "grand_total",
#             "fieldtype": "Currency",
#             "width": 130,
#         },
#         {
#             "label": "Invoice Outstanding (SAR)",
#             "fieldname": "invoice_outstanding",
#             "fieldtype": "Currency",
#             "width": 150,
#         },
#         {
#             "label": "Customer",
#             "fieldname": "customer",
#             "fieldtype": "Link",
#             "options": "Customer",
#             "width": 170,
#         },
#         {
#             "label": "Customer Name",
#             "fieldname": "customer_name",
#             "fieldtype": "Data",
#             "width": 220,
#         },
#         {
#             "label": "Customer Group",
#             "fieldname": "customer_group",
#             "fieldtype": "Link",
#             "options": "Customer Group",
#             "width": 150,
#         },
#         {
#             "label": "Territory",
#             "fieldname": "territory",
#             "fieldtype": "Link",
#             "options": "Territory",
#             "width": 130,
#         },
#         {
#             "label": "Credit Type",
#             "fieldname": "credit_type",
#             "fieldtype": "Data",
#             "width": 110,
#         },
#         {
#             "label": "Salesman Name",
#             "fieldname": "salesman_name",
#             "fieldtype": "Data",
#             "width": 200,
#         },
#         {
#             "label": "Salesman (User)",
#             "fieldname": "salesman_user",
#             "fieldtype": "Link",
#             "options": "User",
#             "width": 160,
#         },
#         {
#             "label": "Credit Limit (SAR)",
#             "fieldname": "credit_limit",
#             "fieldtype": "Currency",
#             "width": 140,
#         },
#         {
#             "label": "Customer Used Credit (SAR)",
#             "fieldname": "customer_used_credit",
#             "fieldtype": "Currency",
#             "width": 170,
#         },
#         {
#             "label": "Remaining Limit (SAR)",
#             "fieldname": "remaining_credit",
#             "fieldtype": "Currency",
#             "width": 160,
#         },
#     ]


# def get_data(filters, settings):
#     company = (filters.get("company") or "").strip()
#     duration = (filters.get("duration") or "Last 30 Days").strip()
#     customer_group = (filters.get("customer_group") or "").strip()
#     credit_type_filter = (filters.get("credit_type") or "").strip()  # '', 'Temp Credit', 'Credit'
#     salesman_user_filter = (filters.get("salesman_user") or "").strip()
#     customer_filter = (filters.get("customer") or "").strip()
#     territory_filter = (filters.get("territory") or "").strip()
#     show_only_over_limit = int(filters.get("show_only_over_limit") or 0)

#     if not company:
#         return []

#     date_limit = get_date_limit(duration)

#     # 1) Pull ALL unpaid invoices (invoice-wise)
#     inv_rows = _get_unpaid_invoices(
#         company=company,
#         date_limit=date_limit,
#         customer_group=customer_group,
#         salesman_user=salesman_user_filter,
#         customer=customer_filter,
#         territory=territory_filter,
#     )
#     if not inv_rows:
#         return []

#     customers_list = sorted({r["customer"] for r in inv_rows if r.get("customer")})

#     # 2) Identify Temp Credit customers
#     temp_flags = _get_temp_customer_flags(customers_list, settings)

#     # 3) Policies + normal credit limits
#     temp_policies = _get_policies_for_customers(customers_list)
#     credit_limits = _get_standard_credit_limits(company, customer_group)

#     # 4) Customer master (for name/group/territory)
#     cust_map = {
#         c.name: c
#         for c in frappe.get_all(
#             "Customer",
#             filters={"name": ["in", customers_list]},
#             fields=["name", "customer_name", "customer_group", "territory"],
#             limit_page_length=100000,
#         )
#     }

#     # 5) Customer totals (within the same filtered invoice set)
#     customer_outstanding_sum = {}
#     salesman_for_customer = {}
#     for r in inv_rows:
#         cust = r["customer"]
#         customer_outstanding_sum[cust] = customer_outstanding_sum.get(cust, 0.0) + flt(r["outstanding_amount"])
#         # keep last seen salesman info (fine for display)
#         salesman_for_customer[cust] = {
#             "salesman_user": (r.get("owner") or "").strip(),
#             "salesman_name": (r.get("salesman_name") or "").strip(),
#         }

#     # 6) Build final invoice-wise rows
#     out = []
#     for inv in inv_rows:
#         cust = inv["customer"]
#         cdoc = cust_map.get(cust)
#         if not cdoc:
#             continue

#         is_temp = 1 if temp_flags.get(cust) else 0
#         credit_type = "Temp Credit" if is_temp else "Credit"

#         # Credit Type filter
#         if credit_type_filter == "Temp Credit" and not is_temp:
#             continue
#         if credit_type_filter == "Credit" and is_temp:
#             continue

#         # Compute customer credit limit
#         if is_temp:
#             pol = temp_policies.get(cust) or {}
#             credit_limit = _effective_flt(pol.get("credit_limit_override"), settings["default_customer_limit"])
#         else:
#             credit_limit = flt(credit_limits.get(cust) or 0)

#         # For Credit filter, require credit limit > 0
#         if credit_type_filter == "Credit" and credit_limit <= 0:
#             continue

#         cust_used = flt(customer_outstanding_sum.get(cust) or 0)
#         remaining = flt(credit_limit) - cust_used

#         # Optional filter: only customers over limit
#         if show_only_over_limit and remaining >= 0:
#             continue

#         sm = salesman_for_customer.get(cust) or {}
#         salesman_user = (sm.get("salesman_user") or "").strip()
#         salesman_name = (sm.get("salesman_name") or "").strip() or salesman_user

#         out.append(
#             {
#                 "sales_invoice": inv["name"],
#                 "posting_date": inv.get("posting_date"),
#                 "grand_total": flt(inv.get("grand_total") or 0),
#                 "invoice_outstanding": flt(inv.get("outstanding_amount") or 0),
#                 "customer": cust,
#                 "customer_name": cdoc.customer_name,
#                 "customer_group": cdoc.customer_group,
#                 "territory": cdoc.territory,
#                 "credit_type": credit_type,
#                 "salesman_user": salesman_user,
#                 "salesman_name": salesman_name,
#                 "credit_limit": credit_limit,
#                 "customer_used_credit": cust_used,
#                 "remaining_credit": remaining,
#             }
#         )

#     # Sort: newest invoices first
#     out.sort(key=lambda d: (d.get("posting_date") or getdate("1900-01-01"), d.get("sales_invoice") or ""), reverse=True)
#     return out


# # ---------------- Charts & Summary ----------------

# def _customer_agg(data):
#     """
#     Aggregate invoice-wise rows into customer-level totals.
#     Prevents double-counting credit_limit in summary/chart.
#     """
#     agg = {}
#     for r in data:
#         cust = r.get("customer")
#         if not cust:
#             continue
#         if cust not in agg:
#             agg[cust] = {
#                 "customer": cust,
#                 "salesman_name": (r.get("salesman_name") or r.get("salesman_user") or "Not Set").strip(),
#                 "salesman_user": (r.get("salesman_user") or "").strip(),
#                 "credit_limit": flt(r.get("credit_limit")),
#                 "used_credit": 0.0,
#             }
#         agg[cust]["used_credit"] += flt(r.get("invoice_outstanding"))
#         # keep max credit_limit (safe)
#         agg[cust]["credit_limit"] = max(agg[cust]["credit_limit"], flt(r.get("credit_limit")))
#     return agg


# def get_chart(data, filters=None):
#     if not data:
#         return None

#     filters = filters or {}
#     summary_mode = (filters.get("summary_mode") or "Salesman Wise").strip()
#     cust_agg = _customer_agg(data)

#     if summary_mode == "Customer Wise":
#         rows = list(cust_agg.values())
#         rows.sort(key=lambda x: flt(x["used_credit"]), reverse=True)
#         top = rows[:10]
#         labels = [r["customer"] for r in top]
#         used_values = [round(flt(r["used_credit"]), 2) for r in top]
#         limit_values = [round(flt(r["credit_limit"]), 2) for r in top]
#     else:
#         # Salesman Wise
#         sm_agg = {}
#         for c in cust_agg.values():
#             key = (c.get("salesman_name") or c.get("salesman_user") or "Not Set").strip()
#             if key not in sm_agg:
#                 sm_agg[key] = {"used_credit": 0.0, "credit_limit": 0.0}
#             sm_agg[key]["used_credit"] += flt(c.get("used_credit"))
#             sm_agg[key]["credit_limit"] += flt(c.get("credit_limit"))

#         rows = [{"salesman": k, **v} for k, v in sm_agg.items()]
#         rows.sort(key=lambda x: flt(x["used_credit"]), reverse=True)
#         top = rows[:10]

#         labels = [r["salesman"] for r in top]
#         used_values = [round(flt(r["used_credit"]), 2) for r in top]
#         limit_values = [round(flt(r["credit_limit"]), 2) for r in top]

#     if not labels:
#         return None

#     return {
#         "data": {
#             "labels": labels,
#             "datasets": [
#                 {"name": "Used Credit (SAR)", "values": used_values},
#                 {"name": "Credit Limit (SAR)", "values": limit_values},
#             ],
#         },
#         "type": "bar",
#         "height": 300,
#         "colors": None,
#     }


# def get_report_summary(data):
#     if not data:
#         return []

#     cust_agg = _customer_agg(data)

#     total_used = sum(flt(v["used_credit"]) for v in cust_agg.values())
#     total_limit = sum(flt(v["credit_limit"]) for v in cust_agg.values())
#     total_remaining = sum(flt(v["credit_limit"]) - flt(v["used_credit"]) for v in cust_agg.values())

#     return [
#         {"label": "Total Used Credit", "value": round(total_used, 2), "indicator": "Orange"},
#         {"label": "Total Credit Limit", "value": round(total_limit, 2), "indicator": "Blue"},
#         {"label": "Total Remaining Limit", "value": round(total_remaining, 2), "indicator": "Green"},
#     ]


# # ---------------- Duration helper ----------------

# def get_date_limit(duration):
#     today = getdate(nowdate())

#     if duration == "Today":
#         return today
#     if duration == "Last 30 Days":
#         return add_days(today, -30)
#     if duration == "Last 60 Days":
#         return add_days(today, -60)
#     if duration == "Last 90 Days":
#         return add_days(today, -90)

#     return None  # All


# # ---------------- SQL Helpers ----------------

# def _get_unpaid_invoices(company, date_limit=None, customer_group=None, salesman_user=None, customer=None, territory=None):
#     params = {"company": company}
#     cond = ""

#     if date_limit:
#         cond += " AND si.posting_date >= %(date_limit)s"
#         params["date_limit"] = date_limit

#     if salesman_user:
#         cond += " AND si.owner = %(salesman_user)s"
#         params["salesman_user"] = salesman_user

#     if customer:
#         cond += " AND si.customer = %(customer)s"
#         params["customer"] = customer

#     # Need Customer join if filtering by customer_group/territory
#     join_customer = ""
#     if customer_group or territory:
#         join_customer = "INNER JOIN `tabCustomer` c ON c.name = si.customer"

#     if customer_group:
#         cond += " AND c.customer_group = %(customer_group)s"
#         params["customer_group"] = customer_group

#     if territory:
#         cond += " AND c.territory = %(territory)s"
#         params["territory"] = territory

#     rows = frappe.db.sql(
#         f"""
#         SELECT
#             si.name,
#             si.customer,
#             si.posting_date,
#             si.grand_total,
#             si.outstanding_amount,
#             si.owner,
#             u.full_name AS salesman_name
#         FROM `tabSales Invoice` si
#         {join_customer}
#         LEFT JOIN `tabUser` u ON u.name = si.owner
#         WHERE
#             si.docstatus = 1
#             AND IFNULL(si.is_return, 0) = 0
#             AND IFNULL(si.outstanding_amount, 0) > 0
#             AND si.company = %(company)s
#             {cond}
#         ORDER BY si.posting_date DESC, si.modified DESC
#         """,
#         params,
#         as_dict=True,
#     )

#     return rows


# def _get_standard_credit_limits(company, customer_group=None):
#     where_extra = ""
#     params = {"company": company}

#     if customer_group:
#         where_extra = "AND c.customer_group = %(customer_group)s"
#         params["customer_group"] = customer_group

#     rows = frappe.db.sql(
#         f"""
#         SELECT
#             ccl.parent AS customer,
#             MAX(ccl.credit_limit) AS credit_limit
#         FROM `tabCustomer Credit Limit` ccl
#         INNER JOIN `tabCustomer` c ON c.name = ccl.parent
#         WHERE
#             (IFNULL(ccl.company, '') = '' OR ccl.company = %(company)s)
#             {where_extra}
#         GROUP BY ccl.parent
#         """,
#         params,
#         as_dict=True,
#     )

#     return {r.customer: flt(r.credit_limit) for r in rows}


# # ---------------- Temp Credit Helpers ----------------

# def _get_settings():
#     try:
#         s = frappe.get_single("Temp Credit Settings")
#     except Exception:
#         return {
#             "customer_tc_fieldname": "custom_payment_type",
#             "temp_credit_value": "__NO_TEMP_VALUE__",
#             "default_customer_limit": 0,
#         }

#     customer_tc_fieldname = (getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type").strip()
#     temp_credit_value = (getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit").strip()

#     return {
#         "customer_tc_fieldname": customer_tc_fieldname,
#         "temp_credit_value": temp_credit_value,
#         "default_customer_limit": flt(getattr(s, "default_customer_limit", 0)),
#     }


# def _get_temp_customer_flags(customer_names, settings):
#     flags = {}
#     if not customer_names:
#         return flags

#     tc_field = settings["customer_tc_fieldname"]
#     tc_value = settings["temp_credit_value"]

#     rows = frappe.get_all(
#         "Customer",
#         filters={"name": ["in", customer_names], tc_field: tc_value},
#         fields=["name"],
#         limit_page_length=100000,
#     )
#     for r in rows:
#         flags[r.name] = 1
#     return flags


# def _get_policies_for_customers(customer_names):
#     policies = {}
#     if not customer_names:
#         return policies

#     rows = frappe.get_all(
#         "Temp Credit Customer Policy",
#         filters={"customer": ["in", customer_names]},
#         fields=["customer", "enabled", "credit_limit_override"],
#         limit_page_length=100000,
#     )
#     for r in rows:
#         if flt(r.get("enabled", 1)) == 0:
#             continue
#         policies[r.customer] = r
#     return policies


# def _effective_flt(override_value, default_value):
#     ov = flt(override_value)
#     return ov if ov > 0 else flt(default_value)





# import json
# import urllib.parse

# import frappe
# from frappe.utils import flt, add_days, nowdate, getdate


# def execute(filters=None):
#     filters = filters or {}

#     # Full Temp Credit settings (field name + value + default limit)
#     settings = _get_settings()

#     columns = get_columns()
#     data = get_data(filters, settings)

#     # Manual Summary Mode:
#     # - summary_mode = "Salesman Wise"  -> salesman-wise chart
#     # - summary_mode = "Customer Wise" -> top customers chart
#     chart = get_chart(data, filters)
#     report_summary = get_report_summary(data)

#     return columns, data, None, chart, report_summary


# def get_columns():
#     """Customer-wise credit view (like AR Summary, plus salesman)."""
#     return [
#         {
#             "label": "Customer",
#             "fieldname": "customer",
#             "fieldtype": "Link",
#             "options": "Customer",
#             "width": 180,
#         },
#         {
#             "label": "Customer Name",
#             "fieldname": "customer_name",
#             "fieldtype": "Data",
#             "width": 220,
#         },
#         {
#             "label": "Customer Group",
#             "fieldname": "customer_group",
#             "fieldtype": "Link",
#             "options": "Customer Group",
#             "width": 160,
#         },
#         {
#             "label": "Territory",
#             "fieldname": "territory",
#             "fieldtype": "Link",
#             "options": "Territory",
#             "width": 140,
#         },
#         {
#             "label": "Credit Type",
#             "fieldname": "credit_type",
#             "fieldtype": "Data",
#             "width": 110,
#         },
#         {
#             "label": "Salesman Name",
#             "fieldname": "salesman_name",
#             "fieldtype": "Data",
#             "width": 200,
#         },
#         {
#             "label": "Salesman (User)",
#             "fieldname": "salesman_user",
#             "fieldtype": "Link",
#             "options": "User",
#             "width": 160,
#         },
#         {
#             "label": "Credit Limit (SAR)",
#             "fieldname": "credit_limit",
#             "fieldtype": "Currency",
#             "width": 150,
#         },
#         {
#             "label": "Used Credit (SAR)",
#             "fieldname": "used_credit",
#             "fieldtype": "Currency",
#             "width": 150,
#         },
#         {
#             "label": "Remaining Limit (SAR)",
#             "fieldname": "remaining_credit",
#             "fieldtype": "Currency",
#             "width": 160,
#         },
#         {
#             "label": "Open Sales Invoices",
#             "fieldname": "open_invoices_link",
#             "fieldtype": "HTML",
#             "width": 160,
#         },
#     ]


# def get_data(filters, settings):
#     company = (filters.get("company") or "").strip()
#     duration = (filters.get("duration") or "Last 30 Days").strip()
#     customer_group = (filters.get("customer_group") or "").strip()
#     credit_type_filter = (filters.get("credit_type") or "").strip()  # '', 'Temp Credit', 'Credit'
#     salesman_user_filter = (filters.get("salesman_user") or "").strip()

#     if not company:
#         return []

#     # 1) Credit limits per customer (for normal credit customers)
#     credit_limits = _get_standard_credit_limits(company, customer_group)

#     # 2) Outstanding per customer from Sales Invoice (only unpaid invoices)
#     #    includes optional salesman_user filter (si.owner)
#     outstanding_map = _get_outstanding_summary(
#         company=company,
#         duration=duration,
#         customer_group=customer_group,
#         salesman_user=salesman_user_filter,
#     )

#     # Base set = customers with unpaid invoices (for both Credit & Temp Credit)
#     customers_set = set(outstanding_map.keys())
#     if not customers_set:
#         return []

#     customers_list = list(customers_set)

#     # 3) Temp credit flags & per-customer temp policy (limit override)
#     temp_flags = _get_temp_customer_flags(customers_list, settings)
#     temp_policies = _get_policies_for_customers(customers_list)

#     # 4) Customer master
#     customers = frappe.get_all(
#         "Customer",
#         filters={"name": ["in", customers_list]},
#         fields=["name", "customer_name", "customer_group", "territory"],
#         order_by="customer_name asc",
#         limit_page_length=100000,
#     )

#     data = []
#     for c in customers:
#         is_temp = 1 if temp_flags.get(c.name) else 0
#         credit_type = "Temp Credit" if is_temp else "Credit"

#         # Credit Type filter
#         if credit_type_filter == "Temp Credit" and not is_temp:
#             continue
#         if credit_type_filter == "Credit" and is_temp:
#             continue

#         # Compute Credit Limit
#         if is_temp:
#             # Temp Credit limit from policy or default setting
#             pol = temp_policies.get(c.name) or {}
#             credit_limit = _effective_flt(
#                 pol.get("credit_limit_override"),
#                 settings["default_customer_limit"],
#             )
#         else:
#             # Normal credit limit from Customer Credit Limit
#             credit_limit = flt(credit_limits.get(c.name) or 0)

#         # For "Credit" filter we also require a positive credit limit
#         if credit_type_filter == "Credit" and credit_limit <= 0:
#             continue

#         summary = outstanding_map.get(c.name) or {}
#         used_credit = flt(summary.get("outstanding_sum") or 0)
#         remaining = credit_limit - used_credit

#         salesman_user = (summary.get("salesman_user") or "").strip()
#         salesman_name = (summary.get("salesman_name") or "").strip()
#         if not salesman_name:
#             salesman_name = salesman_user or ""

#         # Build "Open Sales Invoices" link
#         open_inv_url = _build_unpaid_invoices_list_url(c.name)

#         data.append(
#             {
#                 "customer": c.name,
#                 "customer_name": c.customer_name,
#                 "customer_group": c.customer_group,
#                 "territory": c.territory,
#                 "credit_type": credit_type,
#                 "salesman_user": salesman_user,
#                 "salesman_name": salesman_name,
#                 "credit_limit": credit_limit,
#                 "used_credit": used_credit,
#                 "remaining_credit": remaining,
#                 "open_invoices_link": f'<a href="{open_inv_url}" target="_blank">Open</a>',
#             }
#         )

#     return data


# # ---------------- Charts & Summary ----------------


# def get_chart(data, filters=None):
#     """
#     Manual Summary Mode:

#     - summary_mode = "Salesman Wise"
#         -> Salesman-wise chart (top 10 salesmen by used credit).
#     - summary_mode = "Customer Wise"
#         -> Top 10 high-used-credit customers (within filters).
#     """
#     if not data:
#         return None

#     filters = filters or {}
#     summary_mode = (filters.get("summary_mode") or "Salesman Wise").strip()

#     if summary_mode == "Customer Wise":
#         return _chart_top_customers(data)

#     # Default: Salesman Wise
#     return _chart_salesman_wise(data)


# def _chart_salesman_wise(data):
#     """
#     Salesman-wise chart:
#     - X-axis: Salesman
#     - Dataset: Used Credit, Credit Limit (sum of customers)
#     - Only top 10 by Used Credit
#     """
#     agg = {}

#     for d in data:
#         key = (d.get("salesman_name") or d.get("salesman_user") or "Not Set").strip()
#         if key not in agg:
#             agg[key] = {
#                 "used_credit": 0.0,
#                 "credit_limit": 0.0,
#             }

#         agg[key]["used_credit"] += flt(d.get("used_credit"))
#         agg[key]["credit_limit"] += flt(d.get("credit_limit"))

#     # Convert to list and sort by used_credit desc
#     rows = [
#         {
#             "salesman": name,
#             "used_credit": vals["used_credit"],
#             "credit_limit": vals["credit_limit"],
#         }
#         for name, vals in agg.items()
#     ]
#     rows.sort(key=lambda x: flt(x["used_credit"]), reverse=True)

#     # Take top 10
#     top = rows[:10]

#     if not top:
#         return None

#     labels = [r["salesman"] for r in top]
#     used_values = [round(flt(r["used_credit"]), 2) for r in top]
#     limit_values = [round(flt(r["credit_limit"]), 2) for r in top]

#     return {
#         "data": {
#             "labels": labels,
#             "datasets": [
#                 {"name": "Used Credit (SAR)", "values": used_values},
#                 {"name": "Credit Limit (SAR)", "values": limit_values},
#             ],
#         },
#         "type": "bar",
#         "height": 300,
#         "colors": None,
#     }


# def _chart_top_customers(data):
#     """
#     Top 10 high-used-credit customers (within current filter context).
#     - X-axis: Customer
#     - Dataset: Used Credit & Credit Limit
#     """
#     sorted_rows = sorted(
#         data,
#         key=lambda d: flt(d.get("used_credit")),
#         reverse=True,
#     )
#     top = sorted_rows[:10]

#     if not top:
#         return None

#     labels = [d["customer"] for d in top]
#     used_values = [round(flt(d.get("used_credit")), 2) for d in top]
#     limit_values = [round(flt(d.get("credit_limit")), 2) for d in top]

#     return {
#         "data": {
#             "labels": labels,
#             "datasets": [
#                 {"name": "Used Credit (SAR)", "values": used_values},
#                 {"name": "Credit Limit (SAR)", "values": limit_values},
#             ],
#         },
#         "type": "bar",
#         "height": 300,
#         "colors": None,
#     }


# def get_report_summary(data):
#     total_used = 0.0
#     total_limit = 0.0
#     total_remaining = 0.0

#     for r in data:
#         used = flt(r.get("used_credit"))
#         limit_ = flt(r.get("credit_limit"))
#         total_used += used
#         total_limit += limit_
#         total_remaining += (limit_ - used)

#     return [
#         {
#             "label": "Total Used Credit",
#             "value": round(total_used, 2),
#             "indicator": "Orange",
#         },
#         {
#             "label": "Total Credit Limit",
#             "value": round(total_limit, 2),
#             "indicator": "Blue",
#         },
#         {
#             "label": "Total Remaining Limit",
#             "value": round(total_remaining, 2),
#             "indicator": "Green",
#         },
#     ]


# # ---------------- Duration helper ----------------


# def get_date_limit(duration):
#     """
#     Convert duration string to a posting_date lower bound.
#     - Today         -> today
#     - Last 30 Days  -> today - 30
#     - Last 60 Days  -> today - 60
#     - Last 90 Days  -> today - 90
#     - All           -> None (no date filter)
#     """
#     today = getdate(nowdate())

#     if duration == "Today":
#         return today
#     if duration == "Last 30 Days":
#         return add_days(today, -30)
#     if duration == "Last 60 Days":
#         return add_days(today, -60)
#     if duration == "Last 90 Days":
#         return add_days(today, -90)

#     return None  # All


# # ---------------- SQL Helpers ----------------


# def _get_standard_credit_limits(company, customer_group=None):
#     """
#     Standard credit limit from Customer Credit Limit.
#     We include:
#       - rows where company matches
#       - rows where company is blank (global limit)
#     """
#     where_extra = ""
#     params = {"company": company}

#     if customer_group:
#         where_extra = "AND c.customer_group = %(customer_group)s"
#         params["customer_group"] = customer_group

#     rows = frappe.db.sql(
#         f"""
#         SELECT
#             ccl.parent AS customer,
#             MAX(ccl.credit_limit) AS credit_limit
#         FROM `tabCustomer Credit Limit` ccl
#         INNER JOIN `tabCustomer` c ON c.name = ccl.parent
#         WHERE
#             (IFNULL(ccl.company, '') = '' OR ccl.company = %(company)s)
#             {where_extra}
#         GROUP BY ccl.parent
#         """,
#         params,
#         as_dict=True,
#     )

#     limits = {}
#     for r in rows:
#         limits[r.customer] = flt(r.credit_limit)

#     return limits


# def _get_outstanding_summary(company, duration, customer_group=None, salesman_user=None):
#     """
#     Open sales invoices only, grouped per customer.
#     Also returns latest invoice owner as salesman.

#     If salesman_user is given, only invoices where si.owner = salesman_user
#     will be included.
#     """
#     result = {}

#     date_limit = get_date_limit(duration)
#     date_condition = ""
#     extra_join = ""
#     extra_where = ""
#     salesman_condition = ""
#     params = {"company": company}

#     if date_limit:
#         date_condition = "AND si.posting_date >= %(date_limit)s"
#         params["date_limit"] = date_limit

#     if customer_group:
#         extra_join = "LEFT JOIN `tabCustomer` c ON c.name = si.customer"
#         extra_where = "AND c.customer_group = %(customer_group)s"
#         params["customer_group"] = customer_group

#     if salesman_user:
#         salesman_condition = "AND si.owner = %(salesman_user)s"
#         params["salesman_user"] = salesman_user

#     rows = frappe.db.sql(
#         f"""
#         WITH inv_base AS (
#             SELECT
#                 si.name AS invoice,
#                 si.customer AS customer,
#                 si.owner AS owner,
#                 si.modified AS modified,
#                 si.outstanding_amount AS outstanding_amount
#             FROM `tabSales Invoice` si
#             {extra_join}
#             WHERE
#                 si.docstatus = 1
#                 AND IFNULL(si.is_return, 0) = 0
#                 AND IFNULL(si.outstanding_amount, 0) > 0
#                 AND si.company = %(company)s
#                 {date_condition}
#                 {extra_where}
#                 {salesman_condition}
#         ),
#         agg AS (
#             SELECT
#                 customer,
#                 COUNT(invoice) AS invoice_count,
#                 SUM(outstanding_amount) AS outstanding_sum
#             FROM inv_base
#             GROUP BY customer
#         ),
#         latest AS (
#             SELECT
#                 b.customer,
#                 b.owner,
#                 u.full_name
#             FROM inv_base b
#             LEFT JOIN `tabUser` u ON u.name = b.owner
#             INNER JOIN (
#                 SELECT customer, MAX(modified) AS mx
#                 FROM inv_base
#                 GROUP BY customer
#             ) x ON x.customer = b.customer AND x.mx = b.modified
#         )
#         SELECT
#             a.customer,
#             a.invoice_count,
#             a.outstanding_sum,
#             l.owner AS salesman_user,
#             l.full_name AS salesman_name
#         FROM agg a
#         LEFT JOIN latest l ON l.customer = a.customer
#         """,
#         params,
#         as_dict=True,
#     )

#     for r in rows:
#         result[r.customer] = {
#             "invoice_count": int(r.invoice_count or 0),
#             "outstanding_sum": flt(r.outstanding_sum),
#             "salesman_user": (r.salesman_user or "").strip(),
#             "salesman_name": (r.salesman_name or "").strip(),
#         }

#     return result


# # ---------------- Temp Credit Helpers ----------------


# def _get_settings():
#     """
#     Read Temp Credit Settings:
#     - customer_tc_fieldname (e.g. custom_payment_type)
#     - temp_credit_value (e.g. Temp Credit)
#     - default_customer_limit (for temp credit)
#     """
#     try:
#         s = frappe.get_single("Temp Credit Settings")
#     except Exception:
#         return {
#             "customer_tc_fieldname": "custom_payment_type",
#             "temp_credit_value": "__NO_TEMP_VALUE__",
#             "default_customer_limit": 0,
#         }

#     customer_tc_fieldname = (
#         getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type"
#     ).strip()
#     temp_credit_value = (
#         getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit"
#     ).strip()

#     return {
#         "customer_tc_fieldname": customer_tc_fieldname,
#         "temp_credit_value": temp_credit_value,
#         "default_customer_limit": flt(getattr(s, "default_customer_limit", 0)),
#     }


# def _get_temp_customer_flags(customer_names, settings):
#     """
#     Return dict {customer_name: 1} for customers marked as Temp Credit
#     using field+value from Temp Credit Settings.
#     """
#     flags = {}
#     if not customer_names:
#         return flags

#     tc_field = settings["customer_tc_fieldname"]
#     tc_value = settings["temp_credit_value"]

#     rows = frappe.get_all(
#         "Customer",
#         filters={
#             "name": ["in", customer_names],
#             tc_field: tc_value,
#         },
#         fields=["name"],
#         limit_page_length=100000,
#     )

#     for r in rows:
#         flags[r.name] = 1

#     return flags


# def _get_policies_for_customers(customer_names):
#     """
#     Temp Credit Customer Policy per customer (for limit override).
#     """
#     policies = {}
#     if not customer_names:
#         return policies

#     rows = frappe.get_all(
#         "Temp Credit Customer Policy",
#         filters={"customer": ["in", customer_names]},
#         fields=["customer", "enabled", "credit_limit_override"],
#         limit_page_length=100000,
#     )

#     for r in rows:
#         if flt(r.get("enabled", 1)) == 0:
#             continue
#         policies[r.customer] = r

#     return policies


# def _effective_flt(override_value, default_value):
#     ov = flt(override_value)
#     return ov if ov > 0 else flt(default_value)


# def _build_unpaid_invoices_list_url(customer):
#     """Clickable link to open all unpaid Sales Invoices for this customer."""
#     filters = [
#         ["Sales Invoice", "customer", "=", customer],
#         ["Sales Invoice", "docstatus", "=", 1],
#         ["Sales Invoice", "is_return", "=", 0],
#         ["Sales Invoice", "outstanding_amount", ">", 0],
#     ]
#     filters_enc = urllib.parse.quote(json.dumps(filters))
#     return f"/app/sales-invoice?filters={filters_enc}"
