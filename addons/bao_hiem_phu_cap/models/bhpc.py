# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BHPCtemplate(models.Model):
    _name = 'bhpc.template'
    _description = 'Mẫu bảo hiểm & phụ cấp'

    name = fields.Char(string='Tên mẫu', required=True)
    default_phu_cap = fields.Float(string='Phụ cấp mặc định (VND)', default=0.0)
    default_bao_hiem_ca_nhan = fields.Float(string='Bảo hiểm cá nhân (%)', default=0.0)
    default_bao_hiem_xa_hoi = fields.Float(string='Bảo hiểm xã hội (%)', default=0.0)


class DanhSachHopDong(models.Model):
    _inherit = 'danh_sach_hop_dong'

    bhpc_template_id = fields.Many2one('bhpc.template', string='Mẫu BH/PC')

    @api.onchange('bhpc_template_id')
    def _onchange_bhpc_template(self):
        if self.bhpc_template_id:
            self.phu_cap = self.bhpc_template_id.default_phu_cap
            self.bao_hiem_ca_nhan = self.bhpc_template_id.default_bao_hiem_ca_nhan
            self.bao_hiem_xa_hoi = self.bhpc_template_id.default_bao_hiem_xa_hoi


class NhanVien(models.Model):
    _inherit = 'nhan_vien'

    bhpc_template_id = fields.Many2one('bhpc.template', string='Mẫu BH/PC')

    @api.onchange('bhpc_template_id')
    def _onchange_bhpc_template_employee(self):
        if self.bhpc_template_id:
            # Nếu nhân viên có template, ưu tiên giá trị template cho trường hiển thị
            self.phu_cap = self.bhpc_template_id.default_phu_cap
            self.bao_hiem_ca_nhan = self.bhpc_template_id.default_bao_hiem_ca_nhan
            self.bao_hiem_xa_hoi = self.bhpc_template_id.default_bao_hiem_xa_hoi
