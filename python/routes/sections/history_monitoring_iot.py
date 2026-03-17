from python.routes.sections.history_log_routes import register_history_log_routes
from python.routes.sections.iot_monitor_routes import register_iot_monitor_routes
from python.routes.sections.monitoring_routes import register_monitoring_routes


def register_history_monitoring_iot_routes(app, templates, ctx):
    register_history_log_routes(app, templates, ctx)
    register_monitoring_routes(app, templates, ctx)
    register_iot_monitor_routes(app, templates, ctx)
