# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    transfer_stage = fields.Selection([
        ('draft', 'Draft'),
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ], string='Inter-Warehouse Stage', default='draft', tracking=True, copy=False)

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        compute='_compute_warehouses',
        store=True
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        compute='_compute_warehouses',
        store=True
    )
    is_interwarehouse = fields.Boolean(
        string='Is Inter-Warehouse Transfer',
        compute='_compute_is_interwarehouse',
        store=True
    )
    transit_picking_id = fields.Many2one(
        'stock.picking',
        string='Linked Inbound Receipt',
        copy=False,
        readonly=True
    )
    origin_dispatch_id = fields.Many2one(
        'stock.picking',
        string='Origin Dispatch Transfer',
        copy=False,
        readonly=True
    )
    can_user_confirm_receipt = fields.Boolean(
        string='Can Current User Confirm Receipt',
        compute='_compute_can_user_confirm_receipt'
    )

    @api.depends('location_id', 'location_dest_id')
    def _compute_warehouses(self):
        for picking in self:
            src_wh = picking.location_id.warehouse_id or (picking.picking_type_id.warehouse_id if picking.picking_type_id else False)
            dest_wh = picking.location_dest_id.warehouse_id
            picking.source_warehouse_id = src_wh
            picking.dest_warehouse_id = dest_wh

    @api.depends('source_warehouse_id', 'dest_warehouse_id', 'location_id', 'location_dest_id')
    def _compute_is_interwarehouse(self):
        for picking in self:
            if picking.source_warehouse_id and picking.dest_warehouse_id and picking.source_warehouse_id != picking.dest_warehouse_id:
                picking.is_interwarehouse = True
            elif picking.location_id.usage == 'transit' and picking.dest_warehouse_id:
                picking.is_interwarehouse = True
            else:
                picking.is_interwarehouse = False

    @api.depends('dest_warehouse_id', 'transfer_stage')
    def _compute_can_user_confirm_receipt(self):
        user = self.env.user
        is_admin = user.has_group('stock.group_stock_manager')
        for picking in self:
            if picking.transfer_stage == 'in_transit':
                if is_admin:
                    picking.can_user_confirm_receipt = True
                elif user.warehouse_id and picking.dest_warehouse_id and user.warehouse_id == picking.dest_warehouse_id:
                    picking.can_user_confirm_receipt = True
                elif picking.dest_warehouse_id in user.allowed_warehouse_ids:
                    picking.can_user_confirm_receipt = True
                else:
                    picking.can_user_confirm_receipt = False
            else:
                picking.can_user_confirm_receipt = False

    def _get_or_create_transit_location(self):
        transit_loc = self.env.ref('warehouse_transfer_confirm.location_inter_warehouse_transit', raise_if_not_found=False)
        if not transit_loc:
            transit_loc = self.env['stock.location'].search([('usage', '=', 'transit')], limit=1)
        if not transit_loc:
            transit_loc = self.env['stock.location'].create({
                'name': 'Inter-Warehouse Transit',
                'usage': 'transit',
                'company_id': False,
            })
        return transit_loc

    def action_dispatch_transit(self):
        """
        Dispatches products from Source Warehouse to Inter-Warehouse Transit.
        Reduces stock from Source Warehouse immediately, but keeps Destination Warehouse stock untouched.
        Creates an incoming receipt at Destination Warehouse waiting for confirmation.
        """
        for picking in self:
            if not picking.move_ids:
                raise UserError(_("Please add products to transfer before dispatching."))
            
            dest_wh = picking.dest_warehouse_id or picking.location_dest_id.warehouse_id
            if not dest_wh:
                raise UserError(_("Destination location must belong to a warehouse (e.g. Cafe Store or Restaurant Store)."))
            
            src_wh = picking.source_warehouse_id or picking.location_id.warehouse_id
            if src_wh and dest_wh and src_wh == dest_wh:
                raise UserError(_("Source and destination warehouses are the same. Use regular internal transfer."))

            transit_loc = self._get_or_create_transit_location()

            # Record final destination for the inbound receipt
            final_dest_location = picking.location_dest_id

            # 1. Update this picking's destination to transit and complete dispatch
            picking.location_dest_id = transit_loc.id
            for move in picking.move_ids:
                move.location_dest_id = transit_loc.id
                for ml in move.move_line_ids:
                    ml.location_dest_id = transit_loc.id
                    if ml.quantity == 0:
                        ml.quantity = move.product_uom_qty
                if move.quantity == 0:
                    move.quantity = move.product_uom_qty

            # Validate dispatch picking (moves stock from WH/Stock -> Transit)
            picking.button_validate()
            picking.write({'transfer_stage': 'in_transit'})

            # 2. Create the inbound receipt for Destination Warehouse (Transit -> CA/Stock)
            in_type = dest_wh.in_type_id or dest_wh.int_type_id
            dest_picking_vals = {
                'picking_type_id': in_type.id,
                'location_id': transit_loc.id,
                'location_dest_id': final_dest_location.id,
                'origin': _("Dispatched from %s") % (picking.name),
                'origin_dispatch_id': picking.id,
                'transfer_stage': 'in_transit',
                'move_ids': []
            }

            for move in picking.move_ids:
                dest_picking_vals['move_ids'].append((0, 0, {
                    'description_picking': move.description_picking or move.product_id.name,
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.quantity or move.product_uom_qty,
                    'product_uom': move.product_uom.id,
                    'location_id': transit_loc.id,
                    'location_dest_id': final_dest_location.id,
                }))

            dest_picking = self.env['stock.picking'].create(dest_picking_vals)
            dest_picking.move_ids._action_confirm()
            dest_picking.move_ids._action_assign()
            picking.write({'transit_picking_id': dest_picking.id})

            # Post message in chatter
            picking.message_post(
                body=_("<b>Goods Dispatched:</b> Stock has left %s and is now in transit.<br/>"
                       "Pending confirmation by %s staff (Inbound Receipt: %s).") % (
                    src_wh.name if src_wh else 'source',
                    dest_wh.name,
                    dest_picking.name
                )
            )
            dest_picking.message_post(
                body=_("<b>Incoming Shipment:</b> Goods are in transit from %s.<br/>"
                       "Please click <b>Confirm Received</b> once physically arrived.") % (
                    src_wh.name if src_wh else 'source'
                )
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Dispatched to Transit'),
                'message': _('Stock successfully dispatched and in transit to destination warehouse.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_confirm_received(self):
        """
        Confirms receipt of in-transit products into destination warehouse inventory.
        Validates the inbound move from Transit to Destination Stock.
        """
        for picking in self:
            user = self.env.user
            is_admin = user.has_group('stock.group_stock_manager')
            if not is_admin and user.warehouse_id and picking.dest_warehouse_id:
                if user.warehouse_id != picking.dest_warehouse_id and picking.dest_warehouse_id not in user.allowed_warehouse_ids:
                    raise UserError(_("You are assigned to %s and cannot confirm receipts for %s.") % (
                        user.warehouse_id.name, picking.dest_warehouse_id.name
                    ))

            for move in picking.move_ids:
                if move.quantity == 0:
                    move.quantity = move.product_uom_qty

            picking.button_validate()
            picking.write({'transfer_stage': 'received'})

            if picking.origin_dispatch_id:
                picking.origin_dispatch_id.write({'transfer_stage': 'received'})
                picking.origin_dispatch_id.message_post(
                    body=_("<b>Receipt Confirmed:</b> %s staff confirmed delivery. Stock is now added to %s inventory.") % (
                        picking.dest_warehouse_id.name if picking.dest_warehouse_id else '',
                        picking.location_dest_id.complete_name
                    )
                )

            picking.message_post(
                body=_("<b>Stock Received:</b> Products successfully received and added to %s inventory by %s.") % (
                    picking.location_dest_id.complete_name, user.name
                )
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Received'),
                'message': _('Products have been confirmed and added to your warehouse inventory!'),
                'type': 'success',
                'sticky': False,
            }
        }
