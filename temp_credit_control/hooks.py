app_name = "temp_credit_control"
app_title = "Temp Credit Control"
app_publisher = "Temp Credit Control"
app_description = "Temp Credit Control"
app_email = "anzar@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "temp_credit_control",
# 		"logo": "/assets/temp_credit_control/logo.png",
# 		"title": "Temp Credit Control",
# 		"route": "/temp_credit_control",
# 		"has_permission": "temp_credit_control.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/temp_credit_control/css/temp_credit_control.css"
# app_include_js = "/assets/temp_credit_control/js/temp_credit_control.js"

# include js, css files in header of web template
# web_include_css = "/assets/temp_credit_control/css/temp_credit_control.css"
# web_include_js = "/assets/temp_credit_control/js/temp_credit_control.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "temp_credit_control/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice_temp_credit.js"
}
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "temp_credit_control/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "temp_credit_control.utils.jinja_methods",
# 	"filters": "temp_credit_control.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "temp_credit_control.install.before_install"
# after_install = "temp_credit_control.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "temp_credit_control.uninstall.before_uninstall"
# after_uninstall = "temp_credit_control.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "temp_credit_control.utils.before_app_install"
# after_app_install = "temp_credit_control.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "temp_credit_control.utils.before_app_uninstall"
# after_app_uninstall = "temp_credit_control.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "temp_credit_control.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Invoice": {
        "validate": "temp_credit_control.services.temp_credit_validator.apply_temp_credit_rules",
        "before_submit": "temp_credit_control.services.temp_credit_validator.apply_temp_credit_rules",
    }
}

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"temp_credit_control.tasks.all"
# 	],
# 	"daily": [
# 		"temp_credit_control.tasks.daily"
# 	],
# 	"hourly": [
# 		"temp_credit_control.tasks.hourly"
# 	],
# 	"weekly": [
# 		"temp_credit_control.tasks.weekly"
# 	],
# 	"monthly": [
# 		"temp_credit_control.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "temp_credit_control.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "temp_credit_control.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "temp_credit_control.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["temp_credit_control.utils.before_request"]
# after_request = ["temp_credit_control.utils.after_request"]

# Job Events
# ----------
# before_job = ["temp_credit_control.utils.before_job"]
# after_job = ["temp_credit_control.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"temp_credit_control.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

