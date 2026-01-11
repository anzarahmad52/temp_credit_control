import frappe
from frappe.utils import flt


def apply_temp_credit_rules(doc, method=None):
    # Only on Sales Invoice
    if doc.doctype != "Sales Invoice":
        return

    # Skip cancelled
    if flt(getattr(doc, "docstatus", 0)) == 2:
        return

    # Skip returns
    if flt(getattr(doc, "is_return", 0)) == 1:
        return

    # Must have customer
    customer = getattr(doc, "customer", None)
    if not customer:
        return

    settings = _get_settings()
    if not settings["enabled"]:
        return

    # Check customer payment type
    tc_fieldname = settings["customer_tc_fieldname"] or "custom_payment_type"
    tc_value = settings["temp_credit_value"] or "Temp Credit"

    custom_payment_type = frappe.db.get_value("Customer", customer, tc_fieldname)
    if (custom_payment_type or "").strip() != (tc_value or "").strip():
        return

    # Customer policy (override + blacklist)
    policy = _get_customer_policy(customer)

    if policy and flt(policy.get("enabled", 1)) == 0:
        return

    if policy and flt(policy.get("is_blacklisted", 0)) == 1:
        reason = (policy.get("blacklist_reason") or "").strip() or "Customer is blacklisted for Temp Credit."
        frappe.throw(f"❌ Temp Credit Blocked!\n\nCustomer: {customer}\nReason: {reason}")

    # Effective limits: use overrides if set, else defaults from settings
    max_invoices = _effective_int(
        policy.get("max_unpaid_invoices_override") if policy else None,
        settings["default_max_unpaid_invoices"],
    )

    max_credit = _effective_flt(
        policy.get("credit_limit_override") if policy else None,
        settings["default_customer_limit"],
    )

    # -------- 1) CUSTOMER LEVEL --------
    invoice_count, total_outstanding = _customer_outstanding(customer)

    current_amount = flt(getattr(doc, "outstanding_amount", 0)) or flt(getattr(doc, "grand_total", 0))

    # Include current invoice in calculation while draft/editing
    # (Avoid double-counting if doc is already submitted)
    if flt(getattr(doc, "docstatus", 0)) == 0:
        invoice_count += 1
        total_outstanding += current_amount

    remaining_invoices = max_invoices - invoice_count
    remaining_credit = max_credit - total_outstanding

    message = (
        f"🧾 Temp Credit Customer Limit Info:\n"
        f"- Customer: {customer}\n"
        f"- Current Invoice: {current_amount:.2f} SAR\n"
        f"- Total Unpaid Invoices (incl. this): {invoice_count}\n"
        f"- Total Outstanding (incl. this): {total_outstanding:.2f} SAR\n"
        f"- Customer Credit Limit: {max_credit:.2f} SAR\n"
        f"- Remaining Customer Credit: {max(remaining_credit, 0):.2f} SAR\n"
        f"- Max Unpaid Invoices: {max_invoices}\n"
        f"- Remaining Invoices: {max(int(remaining_invoices), 0)}"
    )

    # -------- 2) WAREHOUSE LEVEL (accurate: header + items) --------
    warehouse_message = ""
    warehouse_outstanding = 0.0
    warehouse_limit_exceeded = False
    warehouse = None

    if settings["enable_warehouse_limit"]:
        warehouse = doc.get("set_warehouse")

        # If no header warehouse, try first item warehouse
        items = doc.get("items") or []
        if not warehouse and items:
            warehouse = items[0].get("warehouse")

        if warehouse:
            wh_limit = settings["default_warehouse_limit"]

            warehouse_outstanding = _warehouse_tc_outstanding(warehouse, tc_fieldname, tc_value)

            # Include current invoice in warehouse pool while draft
            if flt(getattr(doc, "docstatus", 0)) == 0:
                warehouse_outstanding += current_amount

            wh_remaining = wh_limit - warehouse_outstanding
            warehouse_limit_exceeded = warehouse_outstanding > wh_limit

            warehouse_message = (
                f"\n\n🏬 Warehouse Temp Credit Info ({warehouse}):\n"
                f"- Warehouse Limit: {wh_limit:.2f} SAR\n"
                f"- Total Outstanding Temp Credit (incl. this): {warehouse_outstanding:.2f} SAR\n"
                f"- Remaining Warehouse Temp Credit: {max(wh_remaining, 0):.2f} SAR"
            )

    # -------- 3) SALESMAN LIMIT (optional) --------
    salesman_message = ""
    salesman_limit_exceeded = False

    if settings["enable_salesman_limit"]:
        user = getattr(doc, "owner", None) or frappe.session.user
        sp = _get_salesman_policy(user)

        if sp and flt(sp.get("enabled", 1)) == 1:
            if flt(sp.get("is_blocked", 0)) == 1:
                reason = (sp.get("block_reason") or "").strip() or "Salesman blocked for Temp Credit."
                frappe.throw(f"❌ Temp Credit Blocked!\n\nUser: {user}\nReason: {reason}")

            salesman_limit = flt(sp.get("max_outstanding_limit") or 0)
        else:
            salesman_limit = settings["default_salesman_limit"]

        if salesman_limit > 0:
            used = _salesman_tc_outstanding(user, tc_fieldname, tc_value)

            if flt(getattr(doc, "docstatus", 0)) == 0:
                used += current_amount

            remaining = salesman_limit - used
            salesman_limit_exceeded = used > salesman_limit

            salesman_message = (
                f"\n\n👤 Salesman Temp Credit Info ({user}):\n"
                f"- Salesman Limit: {salesman_limit:.2f} SAR\n"
                f"- Outstanding (incl. this): {used:.2f} SAR\n"
                f"- Remaining: {max(remaining, 0):.2f} SAR"
            )

    # -------- 4) FINAL CHECK --------
    customer_limit_exceeded = (invoice_count > max_invoices) or (total_outstanding > max_credit)

    if customer_limit_exceeded or warehouse_limit_exceeded or salesman_limit_exceeded:
        title = "❌ Temp Credit Limit Exceeded!"
        if customer_limit_exceeded and warehouse_limit_exceeded:
            title = "❌ Customer & Warehouse Temp Credit Limits Exceeded!"
        elif warehouse_limit_exceeded:
            title = "❌ Warehouse Temp Credit Limit Exceeded!"
        elif salesman_limit_exceeded:
            title = "❌ Salesman Temp Credit Limit Exceeded!"

        frappe.throw(title + "\n\n" + message + warehouse_message + salesman_message)

    # Allowed: show popup if enabled
    if settings["show_popup_on_allow"]:
        frappe.msgprint(message + warehouse_message + salesman_message)


# ---------------- Helpers ----------------

def _get_settings():
    s = frappe.get_single("Temp Credit Settings")

    return {
        "enabled": bool(flt(getattr(s, "enabled", 0))),
        "default_customer_limit": flt(getattr(s, "default_customer_limit", 700)),
        "default_max_unpaid_invoices": int(getattr(s, "default_max_unpaid_invoices", 3) or 3),
        "default_warehouse_limit": flt(getattr(s, "default_warehouse_limit", 35000)),
        "show_popup_on_allow": bool(flt(getattr(s, "show_popup_on_allow", 1))),
        "enable_warehouse_limit": bool(flt(getattr(s, "enable_warehouse_limit", 1))),
        "enable_salesman_limit": bool(flt(getattr(s, "enable_salesman_limit", 0))),
        "default_salesman_limit": flt(getattr(s, "default_salesman_limit", 0)),
        "customer_tc_fieldname": (getattr(s, "customer_tc_fieldname", "custom_payment_type") or "custom_payment_type").strip(),
        "temp_credit_value": (getattr(s, "temp_credit_value", "Temp Credit") or "Temp Credit").strip(),
    }


def _get_customer_policy(customer):
    customer = (customer or "").strip()
    if not customer:
        return None
    pol = frappe.db.get_value(
        "Temp Credit Customer Policy",
        customer,  # docname
        ["enabled", "credit_limit_override", "max_unpaid_invoices_override",
         "is_blacklisted", "blacklist_reason"],
        as_dict=True,
    )
    if pol:
        return pol
    return frappe.db.get_value(
        "Temp Credit Customer Policy",
        {"customer": customer},
        ["enabled", "credit_limit_override", "max_unpaid_invoices_override",
         "is_blacklisted", "blacklist_reason"],
        as_dict=True,
    )



def _get_salesman_policy(user):
    return frappe.db.get_value(
        "Temp Credit Salesman Policy",
        {"user": user},
        ["enabled", "max_outstanding_limit", "is_blocked", "block_reason"],
        as_dict=True,
    )


def _customer_outstanding(customer):
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": customer,
            "docstatus": 1,
            "is_return": 0,
            "outstanding_amount": [">", 0],
        },
        fields=["outstanding_amount"],
        limit_page_length=2000,
    )

    invoice_count = 0
    total_outstanding = 0.0

    for inv in invoices:
        invoice_count += 1
        total_outstanding += flt(inv.outstanding_amount)

    return invoice_count, total_outstanding


def _warehouse_tc_outstanding(warehouse, tc_fieldname, tc_value):
    """
    Accurate warehouse TC outstanding:
    - Counts submitted, non-return Sales Invoices with outstanding_amount > 0
    - For Temp Credit customers only
    - Includes invoices where warehouse is set on header (set_warehouse)
    - Includes invoices where warehouse is set on items (Sales Invoice Item.warehouse)
    - Supports invoices with multiple warehouses (counts only matching warehouse)
    NOTE: Full outstanding is counted if invoice has any item in this warehouse.
    """

    # 1) Temp Credit customers
    tc_customers = frappe.get_all(
        "Customer",
        filters={tc_fieldname: tc_value},
        pluck="name",
    )
    if not tc_customers:
        return 0.0

    # 2) Base invoices: submitted unpaid
    base_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": ["in", tc_customers],
            "docstatus": 1,
            "is_return": 0,
            "outstanding_amount": [">", 0],
        },
        fields=["name", "outstanding_amount", "set_warehouse"],
        limit_page_length=3000,
    )
    if not base_invoices:
        return 0.0

    inv_out = {d.name: flt(d.outstanding_amount) for d in base_invoices}

    # 3) Header match
    wh = (warehouse or "").strip()
    header_match = {d.name for d in base_invoices if (d.set_warehouse or "").strip() == wh}

    # 4) Item match (only items for the base invoices)
    item_rows = frappe.get_all(
        "Sales Invoice Item",
        filters={
            "parent": ["in", list(inv_out.keys())],
            "warehouse": warehouse,
        },
        fields=["parent"],
        limit_page_length=10000,
    )
    item_match = {r.parent for r in item_rows}

    matched_invoices = header_match.union(item_match)

    total = 0.0
    for inv_name in matched_invoices:
        total += flt(inv_out.get(inv_name))

    return total


def _salesman_tc_outstanding(user, tc_fieldname, tc_value):
    # Uses invoice owner as salesman (simple)
    tc_customers = frappe.get_all(
        "Customer",
        filters={tc_fieldname: tc_value},
        pluck="name",
    )
    if not tc_customers:
        return 0.0

    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": ["in", tc_customers],
            "owner": user,
            "docstatus": 1,
            "is_return": 0,
            "outstanding_amount": [">", 0],
        },
        fields=["outstanding_amount"],
        limit_page_length=3000,
    )

    total = 0.0
    for r in rows:
        total += flt(r.outstanding_amount)

    return total


def _effective_flt(override_value, default_value):
    ov = flt(override_value)
    return ov if ov > 0 else flt(default_value)


def _effective_int(override_value, default_value):
    try:
        ov = int(override_value)
    except Exception:
        ov = 0
    return ov if ov > 0 else int(default_value or 0)
