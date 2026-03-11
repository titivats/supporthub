from python.routes.sections.admin_machines import register_admin_machines_routes
from python.routes.sections.auth_users import register_auth_user_routes
from python.routes.sections.history_monitoring_iot import (
    register_history_monitoring_iot_routes,
)
from python.routes.sections.problem_match import register_problem_match_routes
from python.routes.sections.ticket_actions import register_ticket_action_routes

__all__ = [
    "register_auth_user_routes",
    "register_admin_machines_routes",
    "register_problem_match_routes",
    "register_ticket_action_routes",
    "register_history_monitoring_iot_routes",
]
