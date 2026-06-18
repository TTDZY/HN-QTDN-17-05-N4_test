# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class DonTu(models.Model):
    _name = 'don_tu'
    _description = 'Đơn từ'
    _rec_name = 'nhan_vien_id'

    nhan_vien_id = fields.Many2one('nhan_vien', string="Nhân viên", required=True)
    ngay_lam_don = fields.Date("Ngày làm đơn", required=True, default=fields.Date.today)
    ngay_ap_dung = fields.Date("Ngày áp dụng", required=True)
    
    trang_thai_duyet = fields.Selection([
        ('cho_duyet', 'Chờ duyệt'),
        ('da_duyet', 'Đã duyệt'),
        ('tu_choi', 'Từ chối'),
    ], string="Trạng thái phê duyệt", default='cho_duyet', required=True)

    loai_don = fields.Selection([
        ('nghi', 'Đơn xin nghỉ'),
        ('di_muon', 'Đơn xin đi muộn'),
        ('ve_som', 'Đơn xin về sớm'),
        ('tang_ca', 'Đơn xin tăng ca'),
    ], string="Loại đơn", required=True)

    # Chuyển từ Date sang Datetime
    # Dùng để ghi nhận thời điểm bắt đầu hoặc kết thúc tăng ca thực tế
    so_gio_tang_ca = fields.Datetime("Thời điểm kết thúc tăng ca")

    # Thời gian cho đi muộn/về sớm (Phút)
    thoi_gian_xin = fields.Float("Thời gian xin (phút)")

    @api.constrains(
        'nhan_vien_id',
        'ngay_ap_dung',
        'trang_thai_duyet',
        'loai_don',
        'thoi_gian_xin',
        'so_gio_tang_ca',
    )
    def _check_request(self):
        for rec in self:
            if rec.loai_don in ('di_muon', 've_som') and rec.thoi_gian_xin <= 0:
                raise ValidationError("Thời gian xin phải lớn hơn 0 phút.")
            if rec.loai_don == 'tang_ca':
                if not rec.so_gio_tang_ca:
                    raise ValidationError("Phải nhập thời điểm kết thúc tăng ca.")
                if fields.Datetime.context_timestamp(rec, rec.so_gio_tang_ca).date() != rec.ngay_ap_dung:
                    raise ValidationError("Thời điểm kết thúc tăng ca phải thuộc ngày áp dụng.")
            if rec.trang_thai_duyet == 'da_duyet':
                duplicate = self.search_count([
                    ('nhan_vien_id', '=', rec.nhan_vien_id.id),
                    ('ngay_ap_dung', '=', rec.ngay_ap_dung),
                    ('loai_don', '=', rec.loai_don),
                    ('trang_thai_duyet', '=', 'da_duyet'),
                    ('id', '!=', rec.id),
                ])
                if duplicate:
                    raise ValidationError("Đã có đơn cùng loại được duyệt cho nhân viên trong ngày này.")

    def _refresh_attendance(self, employee_ids=None, dates=None):
        employee_ids = employee_ids or self.mapped('nhan_vien_id').ids
        dates = dates or self.mapped('ngay_ap_dung')
        attendances = self.env['cham_cong'].sudo().search([
            ('nhan_vien_id', 'in', employee_ids),
            ('ngay_cham_cong', 'in', dates),
        ])
        attendances._compute_don_tu()
        attendances._compute_gio_ca()
        attendances._compute_phut_di_muon()
        attendances._compute_phut_ve_som()
        attendances._compute_trang_thai()
        attendances._refresh_related_payrolls()

    @api.model
    def create(self, vals):
        if not self.env.user.has_group('nhan_su.group_nhan_su_user'):
            vals['trang_thai_duyet'] = 'cho_duyet'
        record = super().create(vals)
        record._refresh_attendance()
        return record

    def write(self, vals):
        if (
            'trang_thai_duyet' in vals
            and not self.env.user.has_group('nhan_su.group_nhan_su_user')
        ):
            raise ValidationError("Chỉ bộ phận HR mới được phê duyệt hoặc từ chối đơn.")
        old_employee_ids = self.mapped('nhan_vien_id').ids
        old_dates = self.mapped('ngay_ap_dung')
        result = super().write(vals)
        self._refresh_attendance(
            employee_ids=list(set(old_employee_ids + self.mapped('nhan_vien_id').ids)),
            dates=list(set(old_dates + self.mapped('ngay_ap_dung'))),
        )
        return result

    def unlink(self):
        employee_ids = self.mapped('nhan_vien_id').ids
        dates = self.mapped('ngay_ap_dung')
        result = super().unlink()
        self._refresh_attendance(employee_ids=employee_ids, dates=dates)
        return result
