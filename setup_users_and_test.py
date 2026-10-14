# -*- coding: utf-8 -*-
import sys
import os

# Add Odoo path
sys.path.insert(0, r"C:\techvizor\TECHVIZOR\odoo19\odoo-19.0")
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', 'odoo.conf'])

from odoo.modules.registry import Registry
registry = Registry('fizzyfox')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})

    print("=== 1. Checking / Updating User Groups ===")
    stock_user_group = env.ref('stock.group_stock_user')
    
    cafe_user = env['res.users'].search([('login', '=', 'cafe')])
    rst_user = env['res.users'].search([('login', '=', 'restaurant')])
    
    cafe_wh = env['stock.warehouse'].search([('code', '=', 'CA')])
    rst_wh = env['stock.warehouse'].search([('code', '=', 'RST')])
    wh_main = env['stock.warehouse'].search([('code', '=', 'WH')])
    
    print(f"Warehouses found: Main={wh_main.name}, Cafe={cafe_wh.name}, Restaurant={rst_wh.name}")
    
    if stock_user_group.id not in cafe_user.group_ids.ids:
        cafe_user.write({'group_ids': [(4, stock_user_group.id)]})
        print("Added stock.group_stock_user to cafe user.")
        
    if stock_user_group.id not in rst_user.group_ids.ids:
        rst_user.write({'group_ids': [(4, stock_user_group.id)]})
        print("Added stock.group_stock_user to restaurant user.")
        
    cafe_user.write({
        'warehouse_id': cafe_wh.id,
        'allowed_warehouse_ids': [(6, 0, [cafe_wh.id])]
    })
    rst_user.write({
        'warehouse_id': rst_wh.id,
        'allowed_warehouse_ids': [(6, 0, [rst_wh.id])]
    })
    print("User warehouse assignments confirmed.")
    cr.commit()

    print("\n=== 2. Setting Up Test Product & Initial Stock ===")
    product = env['product.product'].search([('name', 'ilike', 'Coffee Beans')], limit=1)
    if not product:
        uom_kg = env.ref('uom.product_uom_kgm')
        tmpl = env['product.template'].create({
            'name': 'Coffee Beans (Arabica)',
            'is_storable': True,
            'uom_id': uom_kg.id,
        })
        product = tmpl.product_variant_id
    
    def get_qty(loc):
        quants = env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', loc.id)
        ])
        return sum(quants.mapped('quantity'))

    # Ensure main warehouse has stock
    main_stock_loc = wh_main.lot_stock_id
    cafe_stock_loc = cafe_wh.lot_stock_id
    rst_stock_loc = rst_wh.lot_stock_id
    
    main_qty_before = get_qty(main_stock_loc)
    if main_qty_before < 20:
        env['stock.quant']._update_available_quantity(product, main_stock_loc, 100.0)
        main_qty_before = get_qty(main_stock_loc)

    print(f"Initial Stock: Main ({wh_main.code}) = {get_qty(main_stock_loc)} kg | Cafe ({cafe_wh.code}) = {get_qty(cafe_stock_loc)} kg | RST ({rst_wh.code}) = {get_qty(rst_stock_loc)} kg")

    print("\n=== 3. Creating & Dispatching Inter-Warehouse Transfer (Main -> Cafe) ===")
    transfer_qty = 15.0
    picking = env['stock.picking'].create({
        'picking_type_id': wh_main.int_type_id.id,
        'location_id': main_stock_loc.id,
        'location_dest_id': cafe_stock_loc.id,
        'move_ids': [(0, 0, {
            'description_picking': product.name,
            'product_id': product.id,
            'product_uom_qty': transfer_qty,
            'product_uom': product.uom_id.id,
            'location_id': main_stock_loc.id,
            'location_dest_id': cafe_stock_loc.id,
        })]
    })
    picking.action_confirm()
    picking.action_assign()
    print(f"Transfer created: {picking.name}, State: {picking.state}")

    # Dispatch to transit
    res = picking.action_dispatch_transit()
    print(f"Dispatch executed. Transfer stage: {picking.transfer_stage}")
    inbound_receipt = picking.transit_picking_id
    print(f"Generated Inbound Receipt at Destination: {inbound_receipt.name} (Destination: {inbound_receipt.location_dest_id.complete_name})")

    # Check stock while IN TRANSIT
    transit_loc = inbound_receipt.location_id
    print(f"IN-TRANSIT Stock:")
    print(f" - Main Store: {get_qty(main_stock_loc)} kg")
    print(f" - Inter-Warehouse Transit: {get_qty(transit_loc)} kg")
    print(f" - Cafe Store: {get_qty(cafe_stock_loc)} kg (MUST NOT BE INCREASED YET)")
    assert get_qty(cafe_stock_loc) == 0.0 or get_qty(cafe_stock_loc) < transfer_qty, "Error: Stock should not be in Cafe yet!"

    print("\n=== 4. Checking Visibility from User Perspectives ===")
    # Check Cafe User perspective
    prod_cafe = product.with_user(cafe_user)
    prod_cafe.invalidate_recordset()
    print(f"Cafe User ({cafe_user.login}) perspective:")
    print(f" - has_pending_transit: {prod_cafe.has_pending_transit}")
    print(f" - pending_transit_qty: {prod_cafe.pending_transit_qty} kg")
    print(f" - user_warehouse_name: {prod_cafe.user_warehouse_name}")
    assert prod_cafe.has_pending_transit == True, "Error: Cafe user should see pending transit!"
    assert prod_cafe.pending_transit_qty >= transfer_qty, "Error: Pending transit qty mismatch!"

    # Check Restaurant User perspective
    prod_rst = product.with_user(rst_user)
    prod_rst.invalidate_recordset()
    print(f"Restaurant User ({rst_user.login}) perspective:")
    print(f" - has_pending_transit: {prod_rst.has_pending_transit}")
    print(f" - pending_transit_qty: {prod_rst.pending_transit_qty} kg")
    assert prod_rst.has_pending_transit == False, "Error: Restaurant user should NOT see Cafe's transit!"
    print("Security check passed: Restaurant user cannot see Cafe shipment!")

    print("\n=== 5. Confirming Receipt by Cafe User ===")
    # Cafe user confirms receipt directly from product action
    prod_cafe.action_confirm_product_receipt_now()
    print("action_confirm_product_receipt_now executed successfully by Cafe user!")

    print("\n=== 6. Post-Confirmation Stock Verification ===")
    print(f"FINAL Stock:")
    print(f" - Main Store: {get_qty(main_stock_loc)} kg")
    print(f" - Inter-Warehouse Transit: {get_qty(transit_loc)} kg")
    print(f" - Cafe Store: {get_qty(cafe_stock_loc)} kg (ADDED TO INVENTORY!)")

    prod_cafe.invalidate_recordset()
    print(f"Cafe User perspective after confirmation:")
    print(f" - has_pending_transit: {prod_cafe.has_pending_transit}")
    print(f" - pending_transit_qty: {prod_cafe.pending_transit_qty} kg")
    assert prod_cafe.has_pending_transit == False, "Error: has_pending_transit should be False after receipt!"
    print(f"Transfer stages: Dispatch={picking.transfer_stage}, Receipt={inbound_receipt.transfer_stage}")
    assert inbound_receipt.state == 'done', "Receipt picking state should be done!"

    cr.commit()
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! Workflow fully verified! <<<")
