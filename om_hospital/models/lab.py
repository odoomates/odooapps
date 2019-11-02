# -*- coding: utf-8 -*-

from odoo import models, fields


# Creating New Model/ Database Table
# https://www.youtube.com/watch?v=L6MxDR71_1k&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=2
class HospitalLab(models.Model):
    _name = 'hospital.lab'
    _description = 'Hospital Laboratory'

    name = fields.Char(string="Name", required=True)
    user_id = fields.Many2one('res.users', string='Responsible')
