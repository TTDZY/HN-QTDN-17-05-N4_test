# -*- coding: utf-8 -*-
from odoo import api, fields, models

class NhanVien(models.Model):
    _name = 'nhan_vien'
    _description = 'Thông tin nhân viên'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'ho_va_ten'
    _order = 'ten asc, ngay_sinh desc'

    # --- ĐỊNH DANH ---
    ma_dinh_danh = fields.Char(
        "Mã định danh",
        required=True,
        copy=False,
        readonly=True,
        default='Mới',
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Tài khoản Odoo',
        ondelete='set null',
        copy=False,
        tracking=True,
        help='Liên kết dùng để nhân viên xem dữ liệu cá nhân và sử dụng trợ lý HR.',
    )
    active = fields.Boolean(default=True)
    ho_ten_dem = fields.Char("Họ tên đệm", required=True)
    ten = fields.Char("Tên", required=True)
    ho_va_ten = fields.Char("Họ và tên", compute="_compute_ho_va_ten", store=True)
    anh = fields.Binary("Ảnh đại diện")

    # --- CÁ NHÂN ---
    ngay_sinh = fields.Date("Ngày sinh")
    tuoi = fields.Integer("Tuổi", compute="_compute_tuoi")
    que_quan = fields.Char("Quê quán")
    email = fields.Char("Email")
    so_dien_thoai = fields.Char("Số điện thoại")
    # --- CÔNG VIỆC ---
    luong_co_ban = fields.Float(
        string='Lương cơ bản', 
        related='hop_dong_hien_tai_id.luong_co_ban', 
        store=True, 
        readonly=True,
        help='Lương được lấy tự động từ hợp đồng đang hiệu lực'
    )
    bao_hiem_ca_nhan = fields.Float(
        string='Bảo hiểm cá nhân (%)', 
        related='hop_dong_hien_tai_id.bao_hiem_ca_nhan', 
        store=True, readonly=True
    )
    bao_hiem_xa_hoi = fields.Float(
        string='Bảo hiểm xã hội (%)', 
        related='hop_dong_hien_tai_id.bao_hiem_xa_hoi', 
        store=True, readonly=True
    )
    phu_cap = fields.Float(string='Phụ cấp', 
        related='hop_dong_hien_tai_id.phu_cap', 
        store=True, readonly=True)
    lich_su_cong_tac_ids = fields.One2many("lich_su_cong_tac", "nhan_vien_id", string="Lịch sử công tác")
    danh_sach_chung_chi_bang_cap_ids = fields.One2many("danh_sach_chung_chi_bang_cap", "nhan_vien_id", string="Chứng chỉ bằng cấp")
    
    # --- LIÊN KẾT MODULE KHÁC ---
    danh_sach_hop_dong_ids = fields.One2many('danh_sach_hop_dong', 'nhan_vien_id', string='Danh sách hợp đồng')

    # --- COMPUTE FIELDS ---
    so_nguoi_bang_tuoi = fields.Integer(
        "Số người bằng tuổi",
        compute="_compute_so_nguoi_bang_tuoi",
    )
    
    hop_dong_hien_tai_id = fields.Many2one('danh_sach_hop_dong', string='Hợp đồng hiện tại', compute='_compute_hop_dong_hien_tai', store=True)
    trang_thai_hop_dong = fields.Selection(related='hop_dong_hien_tai_id.trang_thai', string='Trạng thái HĐ', readonly=True)

    # --- CONSTRAINTS ---
    _sql_constraints = [
        ('ma_dinh_danh_unique', 'unique(ma_dinh_danh)', 'Mã định danh nhân viên phải là duy nhất!'),
        ('user_id_unique', 'unique(user_id)', 'Một tài khoản Odoo chỉ được liên kết với một nhân viên!'),
    ]
    nguoi_phu_thuoc_ids = fields.One2many(
    'nguoi_phu_thuoc',
    'nhan_vien_id',
    string='Người phụ thuộc'
    )

    so_nguoi_phu_thuoc = fields.Integer(
        string='Số người phụ thuộc',
        compute='_compute_so_nguoi_phu_thuoc'
    )

    # @api.constrains('tuoi')
    # def _check_tuoi(self):
    #     for record in self:
    #         if record.tuoi < 18:
    #             raise ValidationError("Nhân viên phải từ 18 tuổi trở lên.")

    # --- LOGIC XỬ LÝ ---
    @api.depends('nguoi_phu_thuoc_ids.dang_hieu_luc')
    def _compute_so_nguoi_phu_thuoc(self):
        for rec in self:
            rec.so_nguoi_phu_thuoc = len(
                rec.nguoi_phu_thuoc_ids.filtered(lambda x: x.dang_hieu_luc)
            )
            
    @api.depends("ho_ten_dem", "ten")
    def _compute_ho_va_ten(self):
        for record in self:
            if record.ho_ten_dem and record.ten:
                record.ho_va_ten = f"{record.ho_ten_dem} {record.ten}"
            else:
                record.ho_va_ten = record.ten or record.ho_ten_dem

    @api.depends("ngay_sinh")
    def _compute_tuoi(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.ngay_sinh:
                record.tuoi = 0
                continue
            record.tuoi = (
                today.year
                - record.ngay_sinh.year
                - ((today.month, today.day) < (record.ngay_sinh.month, record.ngay_sinh.day))
            )

    @api.depends("ngay_sinh")
    def _compute_so_nguoi_bang_tuoi(self):
        employees = self.search([('ngay_sinh', '!=', False)])
        age_counts = {}
        for employee in employees:
            today = fields.Date.context_today(employee)
            age = (
                today.year
                - employee.ngay_sinh.year
                - ((today.month, today.day) < (employee.ngay_sinh.month, employee.ngay_sinh.day))
            )
            age_counts[age] = age_counts.get(age, 0) + 1
        for record in self:
            record.so_nguoi_bang_tuoi = max(age_counts.get(record.tuoi, 0) - 1, 0)


    @api.depends('danh_sach_hop_dong_ids.trang_thai', 'danh_sach_hop_dong_ids.luong_co_ban')
    def _compute_hop_dong_hien_tai(self):
        for record in self:
            # Lấy hợp đồng đang hiệu lực
            hop_dong = record.danh_sach_hop_dong_ids.filtered(lambda x: x.trang_thai == 'dang_hieu_luc')
            # Nếu có nhiều hợp đồng hiệu lực (do lỗi data), lấy cái mới nhất
            record.hop_dong_hien_tai_id = hop_dong.sorted('ngay_bat_dau', reverse=True)[0] if hop_dong else False

    @api.model
    def create(self, vals):
        if vals.get('ma_dinh_danh', 'Mới') == 'Mới':
            vals['ma_dinh_danh'] = self.env['ir.sequence'].next_by_code('nhan_su.nhan_vien') or 'Mới'
        return super().create(vals)
