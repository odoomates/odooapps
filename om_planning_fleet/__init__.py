from . import models


def post_init_hook(env):
    """ Existing vehicles get their planning resource and follow their driver. """
    vehicles = env['fleet.vehicle'].with_context(active_test=False).search([])
    vehicles._planning_ensure_resource()
    vehicles.filtered('active')._planning_fleet_follow_driver()
