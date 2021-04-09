# -*- coding: utf-8 -*-

from odoo import fields, models


class IrActionsReportXml(models.Model):
    _inherit = 'ir.actions.report'

    default_print_option = fields.Selection(selection=[
        ('print', 'Print'),
        ('download', 'Download'),
        ('open', 'Open')
    ], string='Default printing option')
