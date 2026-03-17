from python.routes.sections.admin_machine_mutation_routes import (
    register_admin_machine_mutation_routes,
)
from python.routes.sections.admin_machine_page_routes import (
    register_admin_machine_page_routes,
)


def register_admin_machines_routes(app, templates, ctx):
    register_admin_machine_page_routes(app, templates, ctx)
    register_admin_machine_mutation_routes(app, templates, ctx)
