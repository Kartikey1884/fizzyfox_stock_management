# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import models, fields, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    has_pending_transit = fields.Boolean(
        string='Has Pending In-Transit Stock',
        compute='_compute_pending_transit_info',
        search='_search_has_pending_transit'
    )
    pending_transit_qty = fields.Float(
        string='Pending Receipt Quantity',
        compute='_compute_pending_transit_info'
    )
    user_warehouse_name = fields.Char(
        string='User Warehouse Name',
        compute='_compute_pending_transit_info'
    )

    def _get_user_target_warehouses(self):
        user = self.env.user
        if user.warehouse_id:
            return user.warehouse_id
        elif user.allowed_warehouse_ids:
            return user.allowed_warehouse_ids
        elif user.has_group('stock.group_stock_manager'):
            # Admin with no specific warehouse sees all
            return self.env['stock.warehouse'].search([])
        return self.env['stock.warehouse']

    def _compute_pending_transit_info(self):
        target_whs = self._get_user_target_warehouses()
        for tmpl in self:
            if not target_whs:
                tmpl.has_pending_transit = False
                tmpl.pending_transit_qty = 0.0
                tmpl.user_warehouse_name = ''
                continue

            products = tmpl.product_variant_ids
            moves = self.env['stock.move'].sudo().search([
                ('product_id', 'in', products.ids),
                ('state', 'in', ['assigned', 'confirmed']),
                ('location_id.usage', '=', 'transit'),
                ('location_dest_id.warehouse_id', 'in', target_whs.ids)
            ])
            total_qty = sum(m.product_uom_qty for m in moves)
            tmpl.has_pending_transit = bool(moves)
            tmpl.pending_transit_qty = total_qty
            tmpl.user_warehouse_name = ', '.join(target_whs.mapped('name'))

    def _search_has_pending_transit(self, operator, value):
        target_whs = self._get_user_target_warehouses()
        if not target_whs:
            return [('id', '=', False)]
        moves = self.env['stock.move'].sudo().search([
            ('state', 'in', ['assigned', 'confirmed']),
            ('location_id.usage', '=', 'transit'),
            ('location_dest_id.warehouse_id', 'in', target_whs.ids)
        ])
        product_tmpl_ids = moves.mapped('product_id.product_tmpl_id').ids
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [('id', 'in', product_tmpl_ids)]
        else:
            return [('id', 'not in', product_tmpl_ids)]

    def action_confirm_product_receipt_now(self):
        """
        Directly confirms receipt of this product's in-transit shipment into user's warehouse.
        """
        self.ensure_one()
        target_whs = self._get_user_target_warehouses()
        if not target_whs:
            raise UserError(_("No warehouse assigned to your user account. Please contact administrator."))

        products = self.product_variant_ids
        moves = self.env['stock.move'].sudo().search([
            ('product_id', 'in', products.ids),
            ('state', 'in', ['assigned', 'confirmed']),
            ('location_id.usage', '=', 'transit'),
            ('location_dest_id.warehouse_id', 'in', target_whs.ids)
        ])
        if not moves:
            raise UserError(_("No pending in-transit shipments found for this product in your warehouse."))

        pickings = moves.mapped('picking_id')
        for picking in pickings:
            picking.action_confirm_received()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Product Received!'),
                'message': _('Successfully confirmed receipt of %s into %s inventory!') % (
                    self.name,
                    ', '.join(target_whs.mapped('name'))
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }

    def action_open_product_receipt(self):
        """
        Opens the in-transit receipts for this product.
        """
        self.ensure_one()
        target_whs = self._get_user_target_warehouses()
        products = self.product_variant_ids
        moves = self.env['stock.move'].sudo().search([
            ('product_id', 'in', products.ids),
            ('state', 'in', ['assigned', 'confirmed']),
            ('location_id.usage', '=', 'transit'),
            ('location_dest_id.warehouse_id', 'in', target_whs.ids)
        ])
        picking_ids = moves.mapped('picking_id').ids

        if len(picking_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Incoming Transit Receipt'),
                'res_model': 'stock.picking',
                'res_id': picking_ids[0],
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Incoming Transit Receipts'),
                'res_model': 'stock.picking',
                'view_mode': 'list,form',
                'domain': [('id', 'in', picking_ids)],
                'target': 'current',
            }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    has_pending_transit = fields.Boolean(
        string='Has Pending In-Transit Stock',
        compute='_compute_pending_transit_info'
    )
    pending_transit_qty = fields.Float(
        string='Pending Receipt Quantity',
        compute='_compute_pending_transit_info'
    )
    user_warehouse_name = fields.Char(
        string='User Warehouse Name',
        compute='_compute_pending_transit_info'
    )

    def _compute_pending_transit_info(self):
        target_whs = self.env['product.template']._get_user_target_warehouses()
        for product in self:
            if not target_whs:
                product.has_pending_transit = False
                product.pending_transit_qty = 0.0
                product.user_warehouse_name = ''
                continue

            moves = self.env['stock.move'].sudo().search([
                ('product_id', '=', product.id),
                ('state', 'in', ['assigned', 'confirmed']),
                ('location_id.usage', '=', 'transit'),
                ('location_dest_id.warehouse_id', 'in', target_whs.ids)
            ])
            total_qty = sum(m.product_uom_qty for m in moves)
            product.has_pending_transit = bool(moves)
            product.pending_transit_qty = total_qty
            product.user_warehouse_name = ', '.join(target_whs.mapped('name'))

    def action_confirm_product_receipt_now(self):
        return self.product_tmpl_id.action_confirm_product_receipt_now()

    def action_open_product_receipt(self):
        return self.product_tmpl_id.action_open_product_receipt()
