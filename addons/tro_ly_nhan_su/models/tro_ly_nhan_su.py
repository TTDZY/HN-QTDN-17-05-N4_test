# -*- coding: utf-8 -*-
import json
import logging
import re
import unicodedata
from datetime import date

import requests
from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tro_ly_nhan_su_openai_enabled = fields.Boolean(
        string='Dùng OpenAI cho trợ lý nhân sự',
        default=True,
        config_parameter='tro_ly_nhan_su.openai_enabled',
    )
    tro_ly_nhan_su_openai_api_key = fields.Char(
        string='OpenAI API key',
        config_parameter='tro_ly_nhan_su.openai_api_key',
        groups='base.group_system',
    )
    tro_ly_nhan_su_openai_model = fields.Char(
        string='OpenAI model',
        default='gpt-4.1-mini',
        config_parameter='tro_ly_nhan_su.openai_model',
        help='Ví dụ: gpt-4.1-mini hoặc model mới hơn mà tài khoản OpenAI của bạn hỗ trợ.',
    )


class TroLyNhanSu(models.TransientModel):
    _name = 'tro_ly_nhan_su'
    _description = 'Trợ lý AI nhân sự'

    cau_hoi = fields.Text(
        string='Câu hỏi',
        help='Ví dụ: Tháng này tôi đi làm bao nhiêu ngày?',
    )
    cau_tra_loi = fields.Text(string='Trợ lý trả lời', readonly=True)
    nhan_vien_id = fields.Many2one(
        'nhan_vien',
        string='Hồ sơ đang tra cứu',
        default=lambda self: self._get_current_employee(),
        help='HR có thể chọn nhân viên cần tra cứu. Nhân viên thường chỉ tra cứu hồ sơ của chính mình.',
    )
    is_hr_user = fields.Boolean(
        string='Là HR',
        compute='_compute_is_hr_user',
    )

    def _get_current_employee(self):
        """Tìm hồ sơ nhân viên mà không làm hỏng wizard khi module nâng cấp lệch."""
        employee_model = self.env['nhan_vien']
        if 'user_id' in employee_model._fields:
            employee = employee_model.search(
                [('user_id', '=', self.env.user.id)],
                limit=1,
            )
            if employee:
                return employee

        # Tương thích dữ liệu cũ: thử ghép email cho đến khi HR liên kết tài khoản.
        if self.env.user.email and 'email' in employee_model._fields:
            return employee_model.search(
                [('email', '=ilike', self.env.user.email)],
                limit=1,
            )
        return employee_model.browse()

    def _compute_nhan_vien(self):
        employee = self._get_current_employee()
        for wizard in self:
            wizard.nhan_vien_id = employee

    def _compute_is_hr_user(self):
        is_hr = self._is_hr_user()
        for wizard in self:
            wizard.is_hr_user = is_hr

    def _get_allowed_employee(self):
        """Trả về hồ sơ được phép tra cứu, chống sửa wizard để xem dữ liệu người khác."""
        current_employee = self._get_current_employee()
        if self._is_hr_user() and self.nhan_vien_id:
            return self.nhan_vien_id
        return current_employee

    @staticmethod
    def _normalize(text):
        normalized = unicodedata.normalize('NFD', (text or '').lower())
        return ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')

    def _get_period(self, question):
        today = fields.Date.context_today(self)
        normalized = self._normalize(question)
        if 'thang truoc' in normalized:
            previous_month = today - relativedelta(months=1)
            return previous_month.month, previous_month.year

        month_match = re.search(r'\bthang\s*(\d{1,2})\b', normalized)
        year_match = re.search(r'\b(20\d{2})\b', normalized)
        month = int(month_match.group(1)) if month_match else today.month
        year = int(year_match.group(1)) if year_match else today.year
        if month < 1 or month > 12:
            return today.month, today.year
        return month, year

    def _get_period_from_intent(self, intent):
        today = fields.Date.context_today(self)
        month = intent.get('month') or today.month
        year = intent.get('year') or today.year
        try:
            month = int(month)
            year = int(year)
        except (TypeError, ValueError):
            return today.month, today.year
        if month < 1 or month > 12 or year < 2000:
            return today.month, today.year
        return month, year

    @staticmethod
    def _format_money(value):
        return f"{value or 0:,.0f} đồng".replace(',', '.')

    def _is_hr_user(self):
        return self.env.user.has_group('nhan_su.group_nhan_su_user')

    def _get_openai_config(self):
        params = self.env['ir.config_parameter'].sudo()
        enabled = params.get_param('tro_ly_nhan_su.openai_enabled', default='True')
        return {
            'enabled': str(enabled).lower() not in ('0', 'false', 'no', 'off'),
            'api_key': params.get_param('tro_ly_nhan_su.openai_api_key'),
            'model': params.get_param('tro_ly_nhan_su.openai_model') or 'gpt-4.1-mini',
        }

    def _call_openai(self, system_prompt, user_prompt, max_output_tokens=900):
        config = self._get_openai_config()
        if not config['enabled'] or not config['api_key']:
            return False

        response = requests.post(
            'https://api.openai.com/v1/responses',
            headers={
                'Authorization': f"Bearer {config['api_key']}",
                'Content-Type': 'application/json',
            },
            json={
                'model': config['model'],
                'input': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'max_output_tokens': max_output_tokens,
            },
            timeout=25,
        )
        if response.status_code >= 400:
            raise UserError(
                'OpenAI trả về lỗi %s: %s'
                % (response.status_code, response.text[:500])
            )
        payload = response.json()
        if payload.get('output_text'):
            return payload['output_text']

        chunks = []
        for item in payload.get('output', []):
            for content in item.get('content', []):
                text = content.get('text')
                if text:
                    chunks.append(text)
        return '\n'.join(chunks).strip()

    @staticmethod
    def _json_from_text(text):
        if not text:
            return {}
        cleaned = text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        try:
            return json.loads(cleaned)
        except ValueError:
            match = re.search(r'\{.*\}', cleaned, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except ValueError:
                    return {}
        return {}

    def _llm_extract_intent(self, question):
        today = fields.Date.context_today(self)
        system_prompt = """
Bạn là bộ phân tích ý định cho trợ lý nhân sự trong Odoo.
Chỉ trả về JSON hợp lệ, không markdown, không giải thích.
Các topic hợp lệ: attendance, salary, contract, rewards, discipline, overview, unknown.
Nếu người dùng hỏi "tháng này" dùng tháng/năm hiện tại được cung cấp.
Nếu hỏi "tháng trước" tự suy ra tháng/năm trước.
Nếu hỏi so sánh, đặt compare_previous=true.
Nếu thấy tên nhân viên, điền employee_name; nếu không thì null.
""".strip()
        user_prompt = json.dumps({
            'today': today.isoformat(),
            'question': question,
            'schema': {
                'topic': 'attendance|salary|contract|rewards|discipline|overview|unknown',
                'month': 'number or null',
                'year': 'number or null',
                'employee_name': 'string or null',
                'compare_previous': 'boolean',
                'wants_explanation': 'boolean',
                'language': 'vi',
            },
        }, ensure_ascii=False)
        raw = self._call_openai(system_prompt, user_prompt, max_output_tokens=300)
        intent = self._json_from_text(raw)
        if not intent.get('topic'):
            intent['topic'] = 'unknown'
        return intent

    def _find_employee_for_intent(self, intent):
        current_employee = self._get_allowed_employee()
        employee_name = (intent.get('employee_name') or '').strip()
        if employee_name and self._is_hr_user():
            employee = self.env['nhan_vien'].search([
                '|',
                ('ho_va_ten', '=ilike', employee_name),
                ('ho_va_ten', 'ilike', employee_name),
            ], limit=1)
            if employee:
                return employee
        return current_employee

    def _attendance_snapshot(self, employee, month, year):
        start_date = date(year, month, 1)
        end_date = start_date + relativedelta(months=1, days=-1)
        records = self.env['cham_cong'].search([
            ('nhan_vien_id', '=', employee.id),
            ('ngay_cham_cong', '>=', start_date),
            ('ngay_cham_cong', '<=', end_date),
        ])
        working_states = ['di_lam', 'di_muon', 've_som', 'di_muon_ve_som']
        return {
            'period': f'{month:02d}/{year}',
            'total_records': len(records),
            'work_days': len(records.filtered(lambda rec: rec.trang_thai in working_states)),
            'absent_days': len(records.filtered(lambda rec: rec.trang_thai == 'vang_mat')),
            'late_times': len(records.filtered(lambda rec: rec.trang_thai in ['di_muon', 'di_muon_ve_som'])),
            'early_times': len(records.filtered(lambda rec: rec.trang_thai in ['ve_som', 'di_muon_ve_som'])),
            'late_minutes': sum(records.mapped('phut_di_muon')),
            'early_minutes': sum(records.mapped('phut_ve_som')),
        }

    def _salary_snapshot(self, employee, month, year):
        payroll = self.env['bang_luong'].search([
            ('nhan_vien_id', '=', employee.id),
            ('thang', '=', month),
            ('nam', '=', year),
        ], limit=1)
        if not payroll:
            return {'period': f'{month:02d}/{year}', 'exists': False}
        return {
            'period': f'{month:02d}/{year}',
            'exists': True,
            'base_salary': payroll.luong_co_ban,
            'allowance': payroll.phu_cap,
            'work_days': payroll.so_ngay_di_lam,
            'absent_days': payroll.so_ngay_vang,
            'salary_by_workdays': payroll.luong_theo_cong,
            'overtime_hours': payroll.tong_gio_tang_ca,
            'overtime_amount': payroll.tien_tang_ca,
            'reward_amount': payroll.tien_thuong,
            'attendance_penalty': payroll.tien_phat,
            'discipline_deduction': payroll.tien_ky_luat,
            'personal_insurance': payroll.tien_bh_ca_nhan,
            'social_insurance': payroll.tien_bh_xa_hoi,
            'personal_income_tax': payroll.tien_thue_tncn,
            'net_salary': payroll.tong_luong,
            'tax_policy': payroll.thue_id.name if payroll.thue_id else False,
        }

    def _contract_snapshot(self, employee):
        contract = employee.hop_dong_hien_tai_id
        if not contract:
            return {'exists': False}
        return {
            'exists': True,
            'contract_number': contract.so_hop_dong,
            'type': contract.hop_dong_id.ten_hop_dong,
            'start_date': contract.ngay_bat_dau.isoformat() if contract.ngay_bat_dau else False,
            'end_date': contract.ngay_ket_thuc.isoformat() if contract.ngay_ket_thuc else False,
            'status': contract.trang_thai,
            'base_salary': contract.luong_co_ban,
            'allowance': contract.phu_cap,
            'personal_insurance_percent': contract.bao_hiem_ca_nhan,
            'social_insurance_percent': contract.bao_hiem_xa_hoi,
        }

    def _rewards_snapshot(self, employee, month, year):
        rewards = self.env['tien_thuong'].search([
            ('trang_thai', 'in', ['da_duyet', 'da_chi']),
            ('thang', '=', month),
            ('nam', '=', year),
            '|',
            ('kieu_thuong', '=', 'tat_ca'),
            ('nhan_vien_id', '=', employee.id),
        ])
        return {
            'period': f'{month:02d}/{year}',
            'total': sum(rewards.mapped('so_tien')),
            'items': [{
                'code': reward.name,
                'amount': reward.so_tien,
                'reason': reward.ly_do,
                'status': reward.trang_thai,
                'scope': reward.kieu_thuong,
            } for reward in rewards],
        }

    def _discipline_snapshot(self, employee, month, year):
        decisions = self.env['ky_luat'].search([
            ('nhan_vien_id', '=', employee.id),
            ('thang', '=', month),
            ('nam', '=', year),
            ('trang_thai', 'in', ['da_duyet', 'da_ap_dung']),
        ])
        return {
            'period': f'{month:02d}/{year}',
            'deduction_total': sum(decisions.filtered('anh_huong_luong').mapped('so_tien')),
            'items': [{
                'code': decision.name,
                'form': decision.hinh_thuc,
                'reason': decision.ly_do,
                'violation_date': decision.ngay_vi_pham.isoformat() if decision.ngay_vi_pham else False,
                'affects_salary': decision.anh_huong_luong,
                'amount': decision.so_tien,
                'status': decision.trang_thai,
            } for decision in decisions],
        }

    def _hr_context_snapshot(self, employee, intent):
        month, year = self._get_period_from_intent(intent)
        topic = intent.get('topic') or 'unknown'
        snapshot = {
            'employee': {
                'id': employee.id,
                'name': employee.ho_va_ten,
                'code': employee.ma_dinh_danh,
                'email': employee.email,
            },
            'requested_topic': topic,
            'period': f'{month:02d}/{year}',
            'permissions': {
                'current_user_is_hr': self._is_hr_user(),
                'can_view_other_employees': self._is_hr_user(),
            },
        }

        include_all = topic in ('overview', 'unknown')
        if include_all or topic == 'attendance':
            snapshot['attendance'] = self._attendance_snapshot(employee, month, year)
        if include_all or topic == 'salary':
            snapshot['salary'] = self._salary_snapshot(employee, month, year)
        if include_all or topic == 'contract':
            snapshot['contract'] = self._contract_snapshot(employee)
        if include_all or topic == 'rewards':
            snapshot['rewards'] = self._rewards_snapshot(employee, month, year)
        if include_all or topic == 'discipline':
            snapshot['discipline'] = self._discipline_snapshot(employee, month, year)

        if intent.get('compare_previous'):
            previous = date(year, month, 1) - relativedelta(months=1)
            snapshot['previous_period'] = {
                'period': f'{previous.month:02d}/{previous.year}',
                'attendance': self._attendance_snapshot(employee, previous.month, previous.year),
                'salary': self._salary_snapshot(employee, previous.month, previous.year),
                'rewards': self._rewards_snapshot(employee, previous.month, previous.year),
                'discipline': self._discipline_snapshot(employee, previous.month, previous.year),
            }
        return snapshot

    def _answer_with_llm(self, employee, intent):
        snapshot = self._hr_context_snapshot(employee, intent)
        system_prompt = """
Bạn là trợ lý nhân sự nội bộ nói tiếng Việt trong Odoo.
Chỉ trả lời dựa trên JSON dữ liệu được cung cấp, không bịa số liệu.
Nếu thiếu dữ liệu, nói rõ chưa có dữ liệu trên hệ thống.
Giữ câu trả lời ngắn gọn, thân thiện, dễ hiểu.
Với dữ liệu lương, định dạng tiền Việt Nam; giải thích các khoản cộng/trừ nếu người dùng hỏi "vì sao" hoặc "chi tiết".
Không tiết lộ dữ liệu nhân viên khác trừ khi JSON cho biết người dùng hiện tại là HR.
Nếu phát hiện bất thường nghiệp vụ trong dữ liệu, nêu nhẹ là "nên kiểm tra lại".
""".strip()
        user_prompt = json.dumps({
            'question': self.cau_hoi,
            'intent': intent,
            'data': snapshot,
        }, ensure_ascii=False, default=str)
        return self._call_openai(system_prompt, user_prompt, max_output_tokens=1000)

    def _answer_attendance(self, employee, month, year):
        start_date = date(year, month, 1)
        end_date = start_date + relativedelta(months=1, days=-1)
        records = self.env['cham_cong'].search([
            ('nhan_vien_id', '=', employee.id),
            ('ngay_cham_cong', '>=', start_date),
            ('ngay_cham_cong', '<=', end_date),
        ])
        working_states = ['di_lam', 'di_muon', 've_som', 'di_muon_ve_som']
        work_days = len(records.filtered(lambda rec: rec.trang_thai in working_states))
        absent_days = len(records.filtered(lambda rec: rec.trang_thai == 'vang_mat'))
        late_times = len(records.filtered(
            lambda rec: rec.trang_thai in ['di_muon', 'di_muon_ve_som']
        ))
        late_minutes = sum(records.mapped('phut_di_muon'))
        early_minutes = sum(records.mapped('phut_ve_som'))
        return (
            f"Chấm công tháng {month}/{year} của {employee.ho_va_ten}: "
            f"{work_days} ngày đi làm, {absent_days} ngày vắng, "
            f"{late_times} lần đi muộn ({late_minutes:.0f} phút) và "
            f"{early_minutes:.0f} phút về sớm."
        )

    def _answer_salary(self, employee, month, year):
        payroll = self.env['bang_luong'].search([
            ('nhan_vien_id', '=', employee.id),
            ('thang', '=', month),
            ('nam', '=', year),
        ], limit=1)
        if not payroll:
            return f"Chưa có bảng lương tháng {month}/{year} của bạn."
        return (
            f"Lương tháng {month}/{year}: lương cơ bản "
            f"{self._format_money(payroll.luong_co_ban)}, thưởng "
            f"{self._format_money(payroll.tien_thuong)}, tăng ca "
            f"{self._format_money(payroll.tien_tang_ca)}, phạt chấm công "
            f"{self._format_money(payroll.tien_phat)}, khấu trừ kỷ luật "
            f"{self._format_money(payroll.tien_ky_luat)}, thuế TNCN "
            f"{self._format_money(payroll.tien_thue_tncn)}. "
            f"Thực lĩnh: {self._format_money(payroll.tong_luong)}."
        )

    def _answer_contract(self, employee):
        contract = employee.hop_dong_hien_tai_id
        if not contract:
            return 'Bạn chưa có hợp đồng đang hiệu lực trên hệ thống.'
        end_date = contract.ngay_ket_thuc.strftime('%d/%m/%Y') if contract.ngay_ket_thuc else 'không xác định thời hạn'
        return (
            f"Hợp đồng hiện tại: {contract.so_hop_dong}, "
            f"bắt đầu ngày {contract.ngay_bat_dau.strftime('%d/%m/%Y')}, "
            f"kết thúc: {end_date}, lương cơ bản "
            f"{self._format_money(contract.luong_co_ban)}."
        )

    def _answer_rewards(self, employee, month, year):
        rewards = self.env['tien_thuong'].search([
            ('trang_thai', 'in', ['da_duyet', 'da_chi']),
            ('thang', '=', month),
            ('nam', '=', year),
            '|',
            ('kieu_thuong', '=', 'tat_ca'),
            ('nhan_vien_id', '=', employee.id),
        ])
        if not rewards:
            return f"Bạn chưa có khoản khen thưởng được duyệt trong tháng {month}/{year}."
        total = sum(rewards.mapped('so_tien'))
        reasons = '; '.join(filter(None, rewards.mapped('ly_do')))
        return (
            f"Khen thưởng tháng {month}/{year}: {self._format_money(total)}. "
            f"Lý do: {reasons}."
        )

    def _answer_discipline(self, employee, month, year):
        decisions = self.env['ky_luat'].search([
            ('nhan_vien_id', '=', employee.id),
            ('thang', '=', month),
            ('nam', '=', year),
            ('trang_thai', 'in', ['da_duyet', 'da_ap_dung']),
        ])
        if not decisions:
            return f"Bạn không có quyết định kỷ luật được duyệt trong tháng {month}/{year}."
        total = sum(decisions.filtered('anh_huong_luong').mapped('so_tien'))
        reasons = '; '.join(filter(None, decisions.mapped('ly_do')))
        return (
            f"Tháng {month}/{year} có {len(decisions)} quyết định kỷ luật; "
            f"khấu trừ lương {self._format_money(total)}. Nội dung: {reasons}."
        )

    def _answer_rule_based(self, employee):
        question = self._normalize(self.cau_hoi)
        month, year = self._get_period(self.cau_hoi)
        if any(keyword in question for keyword in ['cham cong', 'di muon', 've som', 'vang', 'ngay lam']):
            return self._answer_attendance(employee, month, year)
        if any(keyword in question for keyword in ['luong', 'thuc linh', 'thue', 'bao hiem']):
            return self._answer_salary(employee, month, year)
        if any(keyword in question for keyword in ['hop dong', 'het han']):
            return self._answer_contract(employee)
        if any(keyword in question for keyword in ['thuong', 'khen thuong']):
            return self._answer_rewards(employee, month, year)
        if any(keyword in question for keyword in ['ky luat', 'khau tru', 'vi pham']):
            return self._answer_discipline(employee, month, year)
        return (
            'Mình có thể hỗ trợ tra cứu chấm công, đi muộn, lương, thuế, '
            'hợp đồng, khen thưởng và kỷ luật. Bạn có thể hỏi: '
            '“Lương tháng này của tôi bao nhiêu?”'
        )

    def action_hoi(self):
        self.ensure_one()
        if not (self.cau_hoi or '').strip():
            self.cau_tra_loi = 'Bạn nhập câu hỏi trước nhé. Ví dụ: “Lương tháng này của tôi bao nhiêu?”'
            return self._reopen()

        employee = self._get_allowed_employee()
        if not employee:
            self.cau_tra_loi = (
                'Tài khoản của bạn chưa được liên kết với hồ sơ nhân viên. '
                'Vui lòng nhờ bộ phận nhân sự thiết lập trường “Tài khoản Odoo”.'
            )
            return self._reopen()

        answer = self._answer_rule_based(employee)
        self.cau_tra_loi = answer
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Trợ lý AI nhân sự',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_lam_moi(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Trợ lý AI nhân sự',
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
        }
