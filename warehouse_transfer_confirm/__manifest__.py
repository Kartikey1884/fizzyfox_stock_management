# -*- coding: utf-8 -*-
{
    'name': 'Warehouse In-Transit Transfer & Receipt Confirmation',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': '2-step inter-warehouse transfers with in-transit holding and product-level receipt confirmation',
    'description': """
Warehouse In-Transit Transfer & Confirmation
============================================
* Dispatches stock from Main Warehouse to Inter-Warehouse Transit.
* Stock leaves Main Store inventory immediately, but is NOT yet added to the destination warehouse.
* Assigns specific warehouses to users (e.g. Cafe User -> Cafe Store, Restaurant User -> Restaurant Store).
* Shows a prominent 'Product Received' action/icon on the Product page and In-Transit Receipts view exclusively for the destination warehouse user.
* Only when confirmed by the destination user is stock officially added to that warehouse's inventory.
    """,
    'author': 'Antigravity / Techvizor',
    'license': 'LGPL-3',
    'depends': ['stock', 'product'],
    'data': [
        'data/stock_location_data.xml',
        'security/ir.model.access.csv',
        'security/warehouse_security.xml',
        'views/res_users_views.xml',
        'views/stock_picking_views.xml',
        'views/product_views.xml',
        'wizard/confirm_product_receipt_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
