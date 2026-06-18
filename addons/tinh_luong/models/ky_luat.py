# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class NhanVienKyLuat(models.Model):
    _inherit = 'nhan_vien'

    ky_luat_ids = fields.One2many(
        'ky_luat',
        'nhan_vien_id',
        string='Lịch sử kỷ luật',
    )


class KyLuat(models.Model):
    _name = 'ky_luat'
    _description = 'Quyết định kỷ luật'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'nam desc, thang desc, id desc'

    name = fields.Char(
        string='Mã quyết định',
        compute='_compute_name',
        store=True,
    )
    nhan_vien_id = fields.Many2one(
        'nhan_vien',
        string='Nhân viên',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    hinh_thuc = fields.Selection([
        ('nhac_nho', 'Nhắc nhở'),
        ('khien_trach', 'Khiển trách'),
        ('canh_cao', 'Cảnh cáo'),
        ('khau_tru', 'Khấu trừ/điều chỉnh lương'),
        ('khac', 'Khác'),
    ], string='Hình thức', required=True, default='nhac_nho', tracking=True)
    ly_do = fields.Text(string='Lý do', required=True)
    ngay_vi_pham = fields.Date(string='Ngày vi phạm', required=True)
    thang = fields.Integer(
        string='Tháng áp dụng',
        required=True,
        default=lambda self: date.today().month,
    )
    nam = fields.Integer(
        string='Năm áp dụng',
        required=True,
        default=lambda self: date.today().year,
    )
    anh_huong_luong = fields.Boolean(
        string='Khấu trừ vào lương',
        default=False,
        tracking=True,
    )
    so_tien = fields.Float(string='Số tiền khấu trừ', tracking=True)
    trang_thai = fields.Selection([
        ('nhap', 'Nháp'),
        ('cho_duyet', 'Chờ duyệt'),
        ('da_duyet', 'Đã duyệt'),
        ('da_ap_dung', 'Đã áp dụng'),
        ('huy', 'Đã hủy'),
    ], string='Trạng thái', default='nhap', tracking=True)
    nguoi_de_xuat_id = fields.Many2one(
        'res.users',
        string='Người đề xuất',
        default=lambda self: self.env.user,
        readonly=True,
    )
    nguoi_duyet_id = fields.Many2one('res.users', string='Người duyệt', readonly=True)
    ngay_duyet = fields.Date(string='Ngày duyệt', readonly=True)
    file_bang_chung = fields.Binary(string='Tệp bằng chứng', attachment=True)
    ten_file_bang_chung = fields.Char(string='Tên tệp')
    giai_trinh = fields.Text(string='Giải trình của nhân viên')
    ghi_chu = fields.Text(string='Ghi chú nội bộ')

    @api.depends('nhan_vien_id', 'thang', 'nam')
    def _compute_name(self):
        for rec in self:
            employee_code = rec.nhan_vien_id.ma_dinh_danh or 'NV'
            rec.name = f"KL-{rec.thang:02d}/{rec.nam}-{employee_code}"

    @api.constrains('thang', 'nam', 'so_tien', 'anh_huong_luong')
    def _check_values(self):
        for rec in self:
            if rec.thang < 1 or rec.thang > 12:
                raise ValidationError('Tháng áp dụng phải nằm trong khoảng 1 đến 12.')
            if rec.nam < 2000:
                raise ValidationError('Năm áp dụng không hợp lệ.')
            if rec.so_tien < 0:
                raise ValidationError('Số tiền khấu trừ không được âm.')
            if rec.anh_huong_luong and rec.so_tien <= 0:
                raise ValidationError('Phải nhập số tiền khi quyết định ảnh hưởng đến lương.')

    def _refresh_payroll(self):
        payrolls = self.env['bang_luong'].search([
            ('nhan_vien_id', 'in', self.mapped('nhan_vien_id').ids),
            ('thang', 'in', self.mapped('thang')),
            ('nam', 'in', self.mapped('nam')),
        ])
        payrolls._compute_tien_ky_luat()
        payrolls._compute_luong_final()

    def action_gui_duyet(self):
        self.filtered(lambda rec: rec.trang_thai == 'nhap').write({'trang_thai': 'cho_duyet'})

    def action_duyet(self):
        for rec in self:
            if rec.trang_thai != 'cho_duyet':
                raise ValidationError('Chỉ quyết định đang chờ duyệt mới được phê duyệt.')
            rec.write({
                'trang_thai': 'da_duyet',
                'nguoi_duyet_id': self.env.user.id,
                'ngay_duyet': fields.Date.today(),
            })
        self._refresh_payroll()

    def action_ap_dung(self):
        for rec in self:
            if rec.trang_thai != 'da_duyet':
                raise ValidationError('Quyết định phải được duyệt trước khi áp dụng.')
            rec.trang_thai = 'da_ap_dung'
        self._refresh_payroll()

    def action_huy(self):
        self.filtered(lambda rec: rec.trang_thai != 'da_ap_dung').write({'trang_thai': 'huy'})
        self._refresh_payroll()
