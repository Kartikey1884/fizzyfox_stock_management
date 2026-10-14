# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Assigned Warehouse',
        help='The default warehouse assigned to this user (e.g. Cafe Store or Restaurant Store). '
             'Used to filter transfers and show the Product Received icon.'
    )
    allowed_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'res_users_stock_warehouse_rel',
        'user_id',
        'warehouse_id',
        string='Allowed Warehouses',
        help='Warehouses this user is permitted to manage and confirm receipts for.'
    )

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        if self.warehouse_id and self.warehouse_id not in self.allowed_warehouse_ids:
            self.allowed_warehouse_ids = [(4, self.warehouse_id.id)]
