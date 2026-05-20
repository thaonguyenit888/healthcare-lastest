from django.core.management.base import BaseCommand
from api.models import Role, Permission


PERMISSIONS_DATA = [
    # User
    {'code': 'user.view', 'name': 'Xem người dùng', 'module': 'user'},
    {'code': 'user.create', 'name': 'Tạo người dùng', 'module': 'user'},
    {'code': 'user.edit', 'name': 'Sửa người dùng', 'module': 'user'},
    {'code': 'user.delete', 'name': 'Xóa người dùng', 'module': 'user'},
    # Facility
    {'code': 'facility.view', 'name': 'Xem cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.create', 'name': 'Tạo cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.edit', 'name': 'Sửa cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.delete', 'name': 'Xóa cơ sở y tế', 'module': 'facility'},
    # Patient
    {'code': 'patient.view', 'name': 'Xem bệnh nhân', 'module': 'patient'},
    {'code': 'patient.create', 'name': 'Tạo bệnh nhân', 'module': 'patient'},
    {'code': 'patient.edit', 'name': 'Sửa bệnh nhân', 'module': 'patient'},
    {'code': 'patient.delete', 'name': 'Xóa bệnh nhân', 'module': 'patient'},
    # Examination (khám chữa bệnh)
    {'code': 'examination.view', 'name': 'Xem phiếu khám', 'module': 'examination'},
    {'code': 'examination.create', 'name': 'Tạo phiếu khám', 'module': 'examination'},
    {'code': 'examination.edit', 'name': 'Sửa phiếu khám', 'module': 'examination'},
    {'code': 'examination.delete', 'name': 'Xóa phiếu khám', 'module': 'examination'},
    # Diagnosis
    {'code': 'diagnosis.view', 'name': 'Xem chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.create', 'name': 'Tạo chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.edit', 'name': 'Sửa chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.delete', 'name': 'Xóa chuẩn đoán', 'module': 'diagnosis'},
    # Report
    {'code': 'report.view', 'name': 'Xem báo cáo thống kê', 'module': 'report'},
]

ROLES_DATA = [
    {
        'code': 'admin',
        'name': 'Quản trị viên',
        'description': 'Toàn quyền quản lý hệ thống',
        'permissions': '__all__',
    },
    {
        'code': 'doctor',
        'name': 'Bác sĩ',
        'description': 'Quản lý khám chữa bệnh, chuẩn đoán và xem bệnh nhân',
        'permissions': [
            'patient.view',
            'examination.view', 'examination.create', 'examination.edit', 'examination.delete',
            'diagnosis.view', 'diagnosis.create', 'diagnosis.edit', 'diagnosis.delete',
            'report.view',
        ],
    },
    {
        'code': 'receptionist',
        'name': 'Lễ tân',
        'description': 'Tiếp nhận và quản lý thông tin bệnh nhân',
        'permissions': [
            'patient.view', 'patient.create', 'patient.edit', 'patient.delete',
            'examination.view', 'examination.create', 'examination.edit', 'examination.delete',
            'report.view',
        ],
    },
    {
        'code': 'nurse',
        'name': 'Điều dưỡng / Y tá',
        'description': 'Hỗ trợ chăm sóc và theo dõi bệnh nhân',
        'permissions': [
            'patient.view',
            'examination.view', 'examination.create', 'examination.edit', 'examination.delete',
            'report.view',
        ],
    },
    {
        'code': 'lab_technician',
        'name': 'Kỹ thuật viên xét nghiệm',
        'description': 'Thực hiện và cập nhật kết quả xét nghiệm',
        'permissions': [
            'patient.view',
            'examination.view', 'examination.create', 'examination.edit', 'examination.delete',
            'report.view',
        ],
    },
    {
        'code': 'pharmacist',
        'name': 'Dược sĩ',
        'description': 'Xem thông tin bệnh nhân và chỉ định điều trị',
        'permissions': [
            'patient.view',
            'examination.view',
            'report.view',
        ],
    },
    {
        'code': 'patient',
        'name': 'Bệnh nhân',
        'description': 'Tài khoản bệnh nhân, truy cập giới hạn',
        'permissions': [
            'diagnosis.view',
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed default roles and permissions'

    def handle(self, *args, **options):
        # Create permissions
        created_perms = 0
        for pdata in PERMISSIONS_DATA:
            _, created = Permission.objects.get_or_create(
                code=pdata['code'],
                defaults={'name': pdata['name'], 'module': pdata['module']}
            )
            if created:
                created_perms += 1

        self.stdout.write(f'Permissions: {created_perms} created, {len(PERMISSIONS_DATA) - created_perms} already existed')

        # Create roles
        for rdata in ROLES_DATA:
            role, created = Role.objects.get_or_create(
                code=rdata['code'],
                defaults={'name': rdata['name'], 'description': rdata['description']}
            )

            if rdata['permissions'] == '__all__':
                role.permissions.set(Permission.objects.all())
            else:
                perm_objs = Permission.objects.filter(code__in=rdata['permissions'])
                role.permissions.set(perm_objs)

            status = 'created' if created else 'updated permissions'
            self.stdout.write(f'Role "{role.name}" ({role.code}): {status}')

        self.stdout.write(self.style.SUCCESS('Seed completed!'))
