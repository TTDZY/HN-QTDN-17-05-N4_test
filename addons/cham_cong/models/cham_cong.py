# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, time, timedelta
from pytz import timezone, UTC


class NhanVienInherit(models.Model):
    _inherit = 'nhan_vien'

    cham_cong_ids = fields.One2many(
        'cham_cong', 'nhan_vien_id', string='Lịch sử chấm công'
    )
    so_ngay_lam_thang_nay = fields.Integer(
        "Số ngày làm tháng này",
        compute='_compute_thong_ke_cham_cong',
    )
    so_lan_tre_thang_nay = fields.Integer(
        "Số lần trễ tháng này",
        compute='_compute_thong_ke_cham_cong',
    )

    def _compute_thong_ke_cham_cong(self):
        today = fields.Date.context_today(self)
        start_of_month = today.replace(day=1)
        grouped = self.env['cham_cong'].read_group(
            [
                ('nhan_vien_id', 'in', self.ids),
                ('ngay_cham_cong', '>=', start_of_month),
                ('ngay_cham_cong', '<=', today),
            ],
            ['nhan_vien_id', 'trang_thai'],
            ['nhan_vien_id', 'trang_thai'],
            lazy=False,
        )
        counters = {}
        working_states = {'di_lam', 'di_muon', 've_som', 'di_muon_ve_som'}
        late_states = {'di_muon', 'di_muon_ve_som'}
        for group in grouped:
            employee_id = group['nhan_vien_id'][0]
            state = group['trang_thai']
            values = counters.setdefault(employee_id, {'work': 0, 'late': 0})
            if state in working_states:
                values['work'] += group['__count']
            if state in late_states:
                values['late'] += group['__count']
        for employee in self:
            values = counters.get(employee.id, {})
            employee.so_ngay_lam_thang_nay = values.get('work', 0)
            employee.so_lan_tre_thang_nay = values.get('late', 0)


class BangChamCong(models.Model):
    _name = 'cham_cong'
    _description = 'Bảng chấm công'
    _order = 'ngay_cham_cong desc'
    _rec_name = 'name'

    # =========================
    # THÔNG TIN CƠ BẢN
    # =========================
    name = fields.Char(compute='_compute_name', store=True)

    nhan_vien_id = fields.Many2one(
        'nhan_vien', string='Nhân viên', required=True
    )

    ngay_cham_cong = fields.Date(
        string='Ngày chấm công',
        required=True,
        default=fields.Date.context_today
    )

    # =========================
    # ĐĂNG KÝ CA & ĐƠN TỪ
    # =========================
    dang_ky_ca_lam_id = fields.Many2one(
        'dang_ky_ca_lam_theo_ngay',
        compute='_compute_dang_ky_ca_lam',
        store=True
    )

    ca_lam = fields.Selection(
        related='dang_ky_ca_lam_id.ca_lam',
        store=True
    )

    don_tu_id = fields.Many2one(
        'don_tu',
        compute='_compute_don_tu',
        store=True
    )

    loai_don = fields.Selection(
        related='don_tu_id.loai_don',
        store=True
    )

    thoi_gian_xin = fields.Float(
        related='don_tu_id.thoi_gian_xin',
        store=True
    )

    # =========================
    # GIỜ CA
    # =========================
    gio_vao_ca = fields.Datetime(
        compute='_compute_gio_ca',
        store=True
    )

    gio_ra_ca = fields.Datetime(
        compute='_compute_gio_ca',
        store=True
    )

    # =========================
    # GIỜ THỰC TẾ
    # =========================
    gio_vao = fields.Datetime(string='Giờ vào')
    gio_ra = fields.Datetime(string='Giờ ra')

    # =========================
    # ĐI MUỘN / VỀ SỚM
    # =========================
    phut_di_muon = fields.Float(
        compute='_compute_phut_di_muon',
        store=True
    )

    phut_ve_som = fields.Float(
        compute='_compute_phut_ve_som',
        store=True
    )

    # =========================
    # TRẠNG THÁI
    # =========================
    trang_thai = fields.Selection([
        ('di_lam', 'Đi làm'),
        ('di_muon', 'Đi muộn'),
        ('ve_som', 'Về sớm'),
        ('di_muon_ve_som', 'Đi muộn & về sớm'),
        ('vang_mat', 'Vắng mặt'),
    ], compute='_compute_trang_thai', store=True)

    _sql_constraints = [
        (
            'unique_employee_attendance_date',
            'unique(nhan_vien_id, ngay_cham_cong)',
            'Mỗi nhân viên chỉ được có một bản chấm công trong một ngày!',
        ),
    ]

    def _refresh_related_payrolls(self, employee_ids=None, dates=None):
        employee_ids = employee_ids or self.mapped('nhan_vien_id').ids
        dates = dates or self.mapped('ngay_cham_cong')
        periods = {(work_date.month, work_date.year) for work_date in dates if work_date}
        payroll_model = self.env['bang_luong'].sudo()
        if not employee_ids or not periods or 'bang_luong' not in self.env.registry.models:
            return
        for month, year in periods:
            payrolls = payroll_model.search([
                ('nhan_vien_id', 'in', employee_ids),
                ('thang', '=', month),
                ('nam', '=', year),
            ])
            payrolls._compute_data_cham_cong()
            payrolls._compute_luong_final()

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._refresh_related_payrolls()
        return record

    def write(self, vals):
        old_employee_ids = self.mapped('nhan_vien_id').ids
        old_dates = self.mapped('ngay_cham_cong')
        result = super().write(vals)
        self._refresh_related_payrolls(
            employee_ids=list(set(old_employee_ids + self.mapped('nhan_vien_id').ids)),
            dates=list(set(old_dates + self.mapped('ngay_cham_cong'))),
        )
        return result

    def unlink(self):
        employee_ids = self.mapped('nhan_vien_id').ids
        dates = self.mapped('ngay_cham_cong')
        result = super().unlink()
        self._refresh_related_payrolls(employee_ids=employee_ids, dates=dates)
        return result

    # ==========================================================
    # COMPUTE METHODS
    # ==========================================================

    @api.depends('nhan_vien_id', 'ngay_cham_cong')
    def _compute_name(self):
        for r in self:
            r.name = (
                f"{r.nhan_vien_id.ho_va_ten} - {r.ngay_cham_cong}"
                if r.nhan_vien_id and r.ngay_cham_cong
                else "Chấm công"
            )

    @api.depends('nhan_vien_id', 'ngay_cham_cong')
    def _compute_dang_ky_ca_lam(self):
        for r in self:
            r.dang_ky_ca_lam_id = self.env['dang_ky_ca_lam_theo_ngay'].search([
                ('nhan_vien_id', '=', r.nhan_vien_id.id),
                ('ngay_lam', '=', r.ngay_cham_cong)
            ], limit=1)

    @api.depends('nhan_vien_id', 'ngay_cham_cong')
    def _compute_don_tu(self):
        for r in self:
            r.don_tu_id = self.env['don_tu'].search([
                ('nhan_vien_id', '=', r.nhan_vien_id.id),
                ('ngay_ap_dung', '=', r.ngay_cham_cong),
                ('trang_thai_duyet', '=', 'da_duyet')
            ], limit=1)

    @api.depends('ca_lam', 'ngay_cham_cong', 'don_tu_id')
    def _compute_gio_ca(self):
        for record in self:
            if not record.ngay_cham_cong or not record.ca_lam:
                record.gio_vao_ca = False
                record.gio_ra_ca = False
                continue

            user_tz = self.env.user.tz or 'UTC'
            tz = timezone(user_tz)

            # 1. Xác định giờ vào/ra gốc theo ca
            if record.ca_lam == "Sáng":
                gio_vao_goc, gio_ra_goc = time(7, 30), time(11, 30)
            elif record.ca_lam == "Chiều":
                gio_vao_goc, gio_ra_goc = time(13, 30), time(17, 30)
            else: # Cả ngày
                gio_vao_goc, gio_ra_goc = time(7, 30), time(17, 30)

            dt_vao = tz.localize(datetime.combine(record.ngay_cham_cong, gio_vao_goc)).astimezone(UTC)
            dt_ra = tz.localize(datetime.combine(record.ngay_cham_cong, gio_ra_goc)).astimezone(UTC)

            # 2. LOGIC MỚI: Nếu có đơn tăng ca, giờ ra ca quy định sẽ là mốc trong đơn
            # Lưu ý: so_gio_tang_ca trong DB đã là UTC
            if record.don_tu_id.loai_don == 'tang_ca' and record.don_tu_id.trang_thai_duyet == 'da_duyet':
                if record.don_tu_id.so_gio_tang_ca:
                    dt_ra = record.don_tu_id.so_gio_tang_ca 

            record.gio_vao_ca = dt_vao.replace(tzinfo=None)
            record.gio_ra_ca = dt_ra.replace(tzinfo=None)

    @api.depends('gio_vao', 'gio_vao_ca', 'loai_don', 'thoi_gian_xin')
    def _compute_phut_di_muon(self):
        for r in self:
            if not r.gio_vao or not r.gio_vao_ca:
                r.phut_di_muon = 0
                continue

            goc = max(0, (r.gio_vao - r.gio_vao_ca).total_seconds() / 60)

            if r.loai_don == 'di_muon':
                r.phut_di_muon = max(0, goc - r.thoi_gian_xin)
            else:
                r.phut_di_muon = goc

    @api.depends('gio_ra', 'gio_ra_ca', 'loai_don', 'thoi_gian_xin')
    def _compute_phut_ve_som(self):
        for r in self:
            if not r.gio_ra or not r.gio_ra_ca:
                r.phut_ve_som = 0
                continue

            goc = max(0, (r.gio_ra_ca - r.gio_ra).total_seconds() / 60)

            if r.loai_don == 've_som':
                r.phut_ve_som = max(0, goc - r.thoi_gian_xin)
            else:
                r.phut_ve_som = goc

    @api.depends('gio_vao', 'gio_ra', 'phut_di_muon', 'phut_ve_som')
    def _compute_trang_thai(self):
        for r in self:
            if not r.gio_vao and not r.gio_ra:
                r.trang_thai = 'vang_mat'
            elif r.phut_di_muon > 0 and r.phut_ve_som > 0:
                r.trang_thai = 'di_muon_ve_som'
            elif r.phut_di_muon > 0:
                r.trang_thai = 'di_muon'
            elif r.phut_ve_som > 0:
                r.trang_thai = 've_som'
            else:
                r.trang_thai = 'di_lam'
