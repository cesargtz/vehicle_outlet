# -*- coding: utf-8 -*-

from odoo import api, fields, models


class VehicleOutlet(models.AbstractModel):
    _name = 'vehicle.outlet'

    contract_id = fields.Many2one('sale.order', 'Contrato')
    contract_type = fields.Selection('Tipo de contrato', readonly=True, related="contract_id.contract_type")
    #partner_id = fields.Many2one('res.partner', readonly=True, related="contract_id.partner_id")
    partner_id = fields.Many2one('res.partner', 'Cliente', compute="_compute_partner", store=True)
    street = fields.Char('Dirección', readonly=True, related='partner_id.street')
    contract_state = fields.Selection('Estado de Contrato', readonly=True, related="contract_id.state")
    active = fields.Boolean(default=True, string="Activo")
    date = fields.Date(required=True, default=fields.Date.today)

    hired = fields.Float('Contratado', compute="_compute_hired", readonly=True, store=False)
    delivered = fields.Float('Entregado', compute="_compute_delivered", readonly=True, store=False)
    pending = fields.Float('Pendiente', compute="_compute_pending", readonly=True, store=False)

    owner_id = fields.Many2one('res.partner', 'Propietario',  help="Propietario", readonly=True, states={'capture': [('readonly', False)], 'analysis': [('readonly', False)]})


    product_id = fields.Many2one('Producto', 'product.product', compute="_compute_product_id", readonly=True, store=False)
    location_id = fields.Many2one('stock.location', 'Ubicación')

    exceeded = fields.Boolean('Excedido', readonly=True)

    @api.one
    @api.depends('contract_id')
    def _compute_partner(self):
        self.partner_id = self.contract_id.partner_id

    @api.one
    @api.depends('contract_id')
    def _compute_hired(self):
        self.hired = sum(line.product_uom_qty for line in self.contract_id.order_line)

    @api.one
    @api.depends('contract_id')
    def _compute_delivered(self):
        self.delivered = 0

    @api.one
    @api.depends('contract_id')
    def _compute_pending(self):
        self.pending = self.hired - self.delivered

    @api.one
    @api.depends('contract_id')
    def _compute_product_id(self):
        product_id = False
        for line in self.contract_id.order_line:
            product_id = line.product_id
            break
        self.product_id = product_id

    @api.multi
    def fun_transfer(self):
        self.stock_picking_id = self.env['stock.picking'].search([('origin', '=', self.contract_id.name), ('state', 'in', ['confirmed', 'partially_available'])], order='date', limit=1)
        if self.stock_picking_id:
            self.stock_picking_id.force_assign()
        else:
            self.stock_picking_id = self.env['stock.picking'].search([('origin', '=', self.contract_id.name), ('state', '=', 'assigned')], order='date', limit=1)
        if self.stock_picking_id:
            for move in self.stock_picking_id.move_lines:
                move.location_id = self.location_id
            if self.raw_kilos > self.stock_picking_id.move_lines[0].product_uom_qty:
                self.exceeded = True
            self._do_enter_transfer_details()

    @api.multi
    def fun_ship(self):
        stock_picking_id_cancel = self.env['stock.picking'].search([('origin', '=', self.contract_id.name), ('state', '=', 'assigned')], order='date', limit=1)
        if stock_picking_id_cancel:
            stock_picking_id_cancel.action_cancel()

    @api.multi
    def _do_enter_transfer_details(self):
        picking_id = [self.stock_picking_id.id]
        context = dict(self._context or {})
        context.update({
            'active_model': self._name,
            'active_ids': picking_id,
            'active_id': len(picking_id) and picking_id[0] or False
        })

        created_id = self.env['stock.backorder.confirmation'].with_context(context).create({'picking_id': len(picking_id) and picking_id[0] or False})
        items = []

        if self.owner_id.id:
            self.stock_picking_id.write({'owner_id': self.owner_id.id})
            self.stock_picking_id.action_assign_owner()

        if not self.stock_picking_id.pack_operation_ids:
            self.stock_picking_id.do_prepare_partial()

        for op in self.stock_picking_id.pack_operation_ids:
            op.write({'qty_done':self.raw_kilos/1000, "location_id": self.location_id.id})
            break;
        created_id.process()
