{
    'name': 'Bảo hiểm & Phụ cấp (BHPC)',
    'version': '15.0.1.0.0',
    'summary': 'Module tách quản lý bảo hiểm và phụ cấp, liên kết với hợp đồng và nhân viên',
    'category': 'Human Resources',
    'author': 'Auto',
    'depends': ['base', 'nhan_su', 'tinh_luong'],
    'data': [
        'security/ir.model.access.csv',
        'views/bhpc_views.xml',
        'data/bhpc_demo_data.xml',
        'data/email_template_phieu_luong.xml',
        'data/email_template_verify_email.xml',
        'views/phieu_luong_inherit.xml',
    ],
    'installable': True,
    'application': False,
}
