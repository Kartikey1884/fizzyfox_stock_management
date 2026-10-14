# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ConfirmProductReceiptWizard(models.TransientModel):
    _name = 'confirm.product.receipt.wizard'
    _description = 'Confirm In-Transit Product Receipt'

    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True)
    picking_id = fields.Many2one('stock.picking', string='Inbound Transfer', required=True, readonly=True)
    quantity_to_receive = fields.Float(string='Quantity to Receive', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    source_warehouse_id = fields.Many2one('stock.warehouse', string='Dispatched From', readonly=True)
    destination_warehouse_id = fields.Many2one('stock.warehouse', string='Receiving Warehouse', readonly=True)
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')

        product = False
        if active_model == 'product.template':
            tmpl = self.env['product.template'].browse(active_id)
            product = tmpl.product_variant_id or tmpl.product_variant_ids[:1]
        elif active_model == 'product.product':
            product = self.env['product.product'].browse(active_id)

        if product:
            res['product_id'] = product.id
            res['uom_id'] = product.uom_id.id
            target_whs = self.env.user.warehouse_id or self.env.user.allowed_warehouse_ids
            moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('state', 'in', ['assigned', 'confirmed']),
                ('location_id.usage', '=', 'transit'),
                ('location_dest_id.warehouse_id', 'in', target_whs.ids)
            ], limit=1)
            if moves:
                res['picking_id'] = moves.picking_id.id
                res['quantity_to_receive'] = moves.product_uom_qty
                res['source_warehouse_id'] = moves.picking_id.source_warehouse_id.id or moves.picking_id.origin_dispatch_id.source_warehouse_id.id
                res['destination_warehouse_id'] = moves.location_dest_id.warehouse_id.id
                res['destination_location_id'] = moves.location_dest_id.id
        return res

    def action_confirm_receipt(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("No incoming shipment found to confirm."))
        self.picking_id.action_confirm_received()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Product Received'),
                'message': _('Successfully confirmed %s %s of %s into %s inventory.') % (
                    self.quantity_to_receive,
                    self.uom_id.name,
                    self.product_id.name,
                    self.destination_warehouse_id.name if self.destination_warehouse_id else ''
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }
