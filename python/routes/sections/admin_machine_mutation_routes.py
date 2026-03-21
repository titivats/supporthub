from python.routes.sections.admin_machine_add_routes import (
    register_admin_machine_add_routes,
)
from python.routes.sections.admin_machine_delete_routes import (
    register_admin_machine_delete_routes,
)


def register_admin_machine_mutation_routes(app, templates, ctx):
    register_admin_machine_add_routes(app, templates, ctx)
    register_admin_machine_delete_routes(app, templates, ctx)
