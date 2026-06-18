# -*- coding: utf-8 -*-
{
    'name': 'Trợ lý AI nhân sự',
    'summary': 'Chatbot nội bộ tra cứu chấm công, lương, hợp đồng và quyết định nhân sự',
    'description': """
        Trợ lý nhân sự nhận diện ý định câu hỏi tiếng Việt và trả lời từ dữ liệu
        Odoo của chính nhân viên đang đăng nhập.
    """,
    'author': 'My Company',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'version': '15.0.1.0.0',
    'depends': ['base', 'web', 'nhan_su', 'cham_cong', 'tinh_luong'],
    'data': [
        'security/ir.model.access.csv',
        'views/tro_ly_nhan_su_views.xml',
    ],
    'installable': True,
    'application': True,
}
