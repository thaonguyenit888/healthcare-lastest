from django.db import migrations


PERMISSIONS_DATA = [
    {'code': 'user.view', 'name': 'Xem người dùng', 'module': 'user'},
    {'code': 'user.create', 'name': 'Tạo người dùng', 'module': 'user'},
    {'code': 'user.edit', 'name': 'Sửa người dùng', 'module': 'user'},
    {'code': 'user.delete', 'name': 'Xóa người dùng', 'module': 'user'},
    {'code': 'facility.view', 'name': 'Xem cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.create', 'name': 'Tạo cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.edit', 'name': 'Sửa cơ sở y tế', 'module': 'facility'},
    {'code': 'facility.delete', 'name': 'Xóa cơ sở y tế', 'module': 'facility'},
    {'code': 'patient.view', 'name': 'Xem bệnh nhân', 'module': 'patient'},
    {'code': 'patient.create', 'name': 'Tạo bệnh nhân', 'module': 'patient'},
    {'code': 'patient.edit', 'name': 'Sửa bệnh nhân', 'module': 'patient'},
    {'code': 'patient.delete', 'name': 'Xóa bệnh nhân', 'module': 'patient'},
    {'code': 'diagnosis.view', 'name': 'Xem chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.create', 'name': 'Tạo chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.edit', 'name': 'Sửa chuẩn đoán', 'module': 'diagnosis'},
    {'code': 'diagnosis.delete', 'name': 'Xóa chuẩn đoán', 'module': 'diagnosis'},
]


def seed_and_migrate(apps, schema_editor):
    Permission = apps.get_model('api', 'Permission')
    Role = apps.get_model('api', 'Role')
    User = apps.get_model('api', 'User')

    # Create permissions
    perm_objects = {}
    for pdata in PERMISSIONS_DATA:
        perm, _ = Permission.objects.get_or_create(
            code=pdata['code'],
            defaults={'name': pdata['name'], 'module': pdata['module']}
        )
        perm_objects[perm.code] = perm

    # Create admin role with all permissions
    admin_role, _ = Role.objects.get_or_create(
        code='admin',
        defaults={'name': 'Quản trị viên', 'description': 'Toàn quyền quản lý hệ thống'}
    )
    admin_role.permissions.set(perm_objects.values())

    # Create doctor role with limited permissions
    doctor_role, _ = Role.objects.get_or_create(
        code='doctor',
        defaults={'name': 'Bác sĩ', 'description': 'Quản lý chuẩn đoán và xem bệnh nhân'}
    )
    doctor_perms = [
        perm_objects[c] for c in [
            'patient.view',
            'diagnosis.view', 'diagnosis.create', 'diagnosis.edit', 'diagnosis.delete',
        ]
    ]
    doctor_role.permissions.set(doctor_perms)

    # Map existing users: role string → role FK id
    role_map = {'admin': admin_role.id, 'doctor': doctor_role.id}
    for user in User.objects.all():
        old_role = user.role  # still a CharField at this point
        if old_role in role_map:
            # Store the role ID as string temporarily (will become FK in next migration)
            User.objects.filter(pk=user.pk).update(role=str(role_map[old_role]))


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_add_permission_role_models'),
    ]

    operations = [
        migrations.RunPython(seed_and_migrate, reverse),
    ]
