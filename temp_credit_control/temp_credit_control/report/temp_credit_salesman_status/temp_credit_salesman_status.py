import frappe
from frappe.utils import flt, add_days, nowdate, getdate


SALESMAN_FIELD = "custom_salesman_user"  # 👈 add this custom field on Sales Invoice


def execute(filters=None):
    filters = filters or {}
    settings = _get_settings()

    columns = get_columns()
    data = get_data(filters, settings)

    chart = get_chart(data)
    summary = get_report_summary(data)

    return columns, data, None, chart, summary


def get_columns():
    return [
        {"label": "Salesman Name", "fieldname": "salesman_name", "fieldtype": "Data", "width": 220},
        {"label": "Salesman (User)", "fieldname": "salesman_user", "fieldtype": "Link", "options": "User", "width": 200},
        {"label": "Salesman Limit (SAR)", "fieldname": "salesman_limit", "fieldtype": "Currency", "width": 160},
        {"label": "Used Temp Credit (SAR)", "fieldname": "used_credit", "fieldtype": "Currency", "width": 170},
        {"label": "Remaining (SAR)", "fieldname": "remaining_limit", "fieldtype": "Currency", "width": 150},
        {"label": "Unpaid Invoices", "fieldname": "unpaid_invoices", "fieldtype": "Int", "width": 130},
        {"label": "Temp Customers", "fieldname": "temp_customers", "fieldtype": "Int", "width": 130},
        {"label": "Over Limit", "fieldname": "over_limit", "fieldtype": "Data", "width": 100},
        {"label": "Blocked", "fieldname": "is_blocked", "fieldtype": "Data", "width": 90},
        {"label": "Block Reason", "fieldname": "block_reason", "fieldtype": "Data", "width": 220},
    ]


def get_data(filters, settings):
    company = (filters.get("company") or "").strip()
    duration = (filters.get("duration") or "Last 30 Days").strip()
    salesman_user_filter = (filters.get("salesman_user") or "").strip()
    show_only_over_limit = flt(filters.get("show_only_over_limit") or 0) == 1
    show_blocked_only = flt(filters.get("show_blocked_only") or 0) == 1

    if not company:
        return []

    tc_field = settings["customer_tc_fieldname"]
    tc_value = settings["temp_credit_value"]

    temp_customers = frappe.db.sql_list(
        f"""
        SELECT name
        FROM `tabCustomer`
        WHERE IFNULL(`{tc_field}`, '') = %s
        """,
        (tc_value,),
    )

    if not temp_customers:
        return []

    salesman_policy_map = _get_salesman_policies()
    default_limit = flt(settings.get("default_salesman_limit") or 0)

    date_limit = get_date_limit(duration)
    date_cond = ""
    params = {"company": company, "temp_customers": tuple(temp_customers)}

    if date_limit:
        params["date_limit"] = date_limit
        date_cond = "AND si.posting_date >= %(date_limit)s"

    # ✅ detect if custom field exists on Sales Invoice table
    has_custom_salesman = frappe.db.has_column("Sales Invoice", SALESMAN_FIELD)

    # build salesman expression
    # If custom_salesman_user exists -> use it, else fallback to owner
    if has_custom_salesman:
        salesman_expr = f"IFNULL(NULLIF(si.`{SALESMAN_FIELD}`,''), si.owner)"
    else:
        salesman_expr = "si.owner"

    salesman_cond = ""
    if salesman_user_filter:
        params["salesman_user"] = salesman_user_filter
        salesman_cond = f"AND {salesman_expr} = %(salesman_user)s"

    rows = frappe.db.sql(
        f"""
        SELECT
            {salesman_expr} AS salesman_user,
            COUNT(si.name) AS unpaid_invoices,
            SUM(si.outstanding_amount) AS used_credit,
            COUNT(DISTINCT si.customer) AS temp_customers
        FROM `tabSales Invoice` si
        WHERE
            si.docstatus = 1
            AND IFNULL(si.is_return, 0) = 0
            AND IFNULL(si.outstanding_amount, 0) > 0
            AND si.company = %(company)s
            AND si.customer IN %(temp_customers)s
            {date_cond}
            {salesman_cond}
        GROUP BY {salesman_expr}
        """,
        params,
        as_dict=True,
    )

    if not rows:
        return []

    # names
    users = [r.salesman_user for r in rows if r.salesman_user]
    urows = frappe.get_all(
        "User",
        filters={"name": ["in", users]},
        fields=["name", "full_name"],
        limit_page_length=100000,
    )
    name_map = {u.name: (u.full_name or "").strip() for u in urows}

    out = []
    for r in rows:
        user = (r.salesman_user or "").strip()
        used = flt(r.used_credit or 0)

        pol = salesman_policy_map.get(user) or {}
        enabled = flt(pol.get("enabled", 1)) == 1
        is_blocked = flt(pol.get("is_blocked", 0)) == 1
        block_reason = (pol.get("block_reason") or "").strip()

        policy_limit = flt(pol.get("max_outstanding_limit") or 0) if enabled else 0
        salesman_limit = policy_limit if policy_limit > 0 else default_limit

        remaining = salesman_limit - used if salesman_limit else (0 - used)
        over_limit = "Yes" if (salesman_limit > 0 and used > salesman_limit) else "No"
        blocked_txt = "Yes" if is_blocked else "No"

        if show_only_over_limit and over_limit != "Yes":
            continue
        if show_blocked_only and blocked_txt != "Yes":
            continue

        out.append(
            {
                "salesman_user": user,
                "salesman_name": name_map.get(user) or user,
                "salesman_limit": salesman_limit,
                "used_credit": used,
                "remaining_limit": remaining,
                "unpaid_invoices": int(r.unpaid_invoices or 0),
                "temp_customers": int(r.temp_customers or 0),
                "over_limit": over_limit,
                "is_blocked": blocked_txt,
                "block_reason": block_reason if is_blocked else "",
            }
        )

    out.sort(key=lambda d: flt(d.get("used_credit")), reverse=True)
    return out


def get_chart(data):
    if not data:
        return None

    top = data[:10]
    labels = [d["salesman_name"] for d in top]
    values = [round(flt(d["used_credit"]), 2) for d in top]

    return {
        "data": {"labels": labels, "datasets": [{"name": "Used Temp Credit (SAR)", "values": values}]},
        "type": "bar",
        "height": 280,
    }


def get_report_summary(data):
    if not data:
        return []
    total_used = sum(flt(r.get("used_credit")) for r in data)
    total_limit = sum(flt(r.get("salesman_limit")) for r in data)
    total_remaining = sum(flt(r.get("remaining_limit")) for r in data)
    return [
        {"label": "Total Used Temp Credit", "value": round(total_used, 2), "indicator": "Orange"},
        {"label": "Total Salesman Limit", "value": round(total_limit, 2), "indicator": "Blue"},
        {"label": "Total Remaining", "value": round(total_remaining, 2), "indicator": "Green"},
    ]


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
    return None


def _get_settings():
    s = frappe.get_single("Temp Credit Settings")
    return {
        "default_salesman_limit": flt(getattr(s, "default_salesman_limit", 0)),
        "customer_tc_fieldname": (getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type").strip(),
        "temp_credit_value": (getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit").strip(),
    }


def _get_salesman_policies():
    rows = frappe.get_all(
        "Temp Credit Salesman Policy",
        fields=["user", "enabled", "max_outstanding_limit", "is_blocked", "block_reason"],
        limit_page_length=100000,
    )
    return {r.user: r for r in rows if r.user}
