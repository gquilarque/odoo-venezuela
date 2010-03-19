# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution	
#    Copyright (C) 2004-2008 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    "name" : "Import Price List",
    "description": """This module allow load a price list from a supplier.""",
    "version" : "1.0",
    "author" : "Netquatro",
    "category" : "Generic Modules/Sales",
    "module": "",
    "website": "http://www.openerp.netquatro.com",
    "depends" : ["base", "product"],
    "init_xml" : [],
    "update_xml" : [
        "load_pricelist_view.xml",
        "load_pricelist_wizard.xml",
        "product_view.xml"
    ],
    "demo_xml" : [],
    "active": False,
    "installable": True,

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

