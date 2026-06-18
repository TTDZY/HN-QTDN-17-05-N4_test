from odoo import models, fields, api
from odoo.exceptions import ValidationError

class DangKyCaLamTheoNgay(models.Model):
    _name = 'dang_ky_ca_lam_theo_ngay'
    _description = "Đăng ký ca làm theo ngày"
    _rec_name = 'ma_dot_ngay'

    _order = 'dot_dang_ky_id desc, ngay_lam asc'

    ma_dot_ngay = fields.Char("Mã đợt ngày", required=True)
    dot_dang_ky_id = fields.Many2one('dot_dang_ky', string="Đợt đăng ký", required=True)
    nhan_vien_id = fields.Many2one('nhan_vien', string="Nhân viên", required=True)
    ngay_lam = fields.Date(string="Ngày làm", required=True)
    ca_lam = fields.Selection([
        ("Sáng", "Sáng"),
        ("Chiều", "Chiều"),
        ("Cả ngày", "Cả Ngày"),
    ], string="Ca làm", required=True)

    _sql_constraints = [
        (
            'unique_employee_work_date',
            'unique(nhan_vien_id, ngay_lam)',
            'Mỗi nhân viên chỉ được đăng ký một ca trong một ngày!',
        ),
        (
            'ma_dot_ngay_unique',
            'unique(ma_dot_ngay)',
            'Mã đợt ngày phải là duy nhất!',
        ),
    ]

    @api.constrains('ngay_lam', 'dot_dang_ky_id')
    def _check_ngay_lam(self):
        for record in self:
            if record.ngay_lam and record.dot_dang_ky_id:
                if record.ngay_lam < record.dot_dang_ky_id.ngay_bat_dau or record.ngay_lam > record.dot_dang_ky_id.ngay_ket_thuc:
                    raise ValidationError(f'Ngày làm phải nằm trong khoảng thời gian của đợt đăng ký (từ {record.dot_dang_ky_id.ngay_bat_dau} đến {record.dot_dang_ky_id.ngay_ket_thuc})')

    @api.constrains('nhan_vien_id', 'dot_dang_ky_id')
    def _check_nhan_vien_in_dot_dang_ky(self):
        for record in self:
            if record.nhan_vien_id not in record.dot_dang_ky_id.nhan_vien_ids:
                raise ValidationError(f'Nhân viên {record.nhan_vien_id.ho_va_ten} không thuộc đợt đăng ký này!')

    def _refresh_attendance(self, employee_ids=None, dates=None):
        employee_ids = employee_ids or self.mapped('nhan_vien_id').ids
        dates = dates or self.mapped('ngay_lam')
        attendances = self.env['cham_cong'].sudo().search([
            ('nhan_vien_id', 'in', employee_ids),
            ('ngay_cham_cong', 'in', dates),
        ])
        attendances._compute_dang_ky_ca_lam()
        attendances._compute_gio_ca()
        attendances._compute_phut_di_muon()
        attendances._compute_phut_ve_som()
        attendances._compute_trang_thai()
        attendances._refresh_related_payrolls()

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._refresh_attendance()
        return record

    def write(self, vals):
        old_employee_ids = self.mapped('nhan_vien_id').ids
        old_dates = self.mapped('ngay_lam')
        result = super().write(vals)
        self._refresh_attendance(
            employee_ids=list(set(old_employee_ids + self.mapped('nhan_vien_id').ids)),
            dates=list(set(old_dates + self.mapped('ngay_lam'))),
        )
        return result

    def unlink(self):
        employee_ids = self.mapped('nhan_vien_id').ids
        dates = self.mapped('ngay_lam')
        result = super().unlink()
        self._refresh_attendance(employee_ids=employee_ids, dates=dates)
        return result
