from django.db import models
from django.contrib.auth.models import AbstractUser

from healthcare import settings
import uuid


class Service(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('kham_benh', 'Khám bệnh'),
        ('xet_nghiem', 'Xét nghiệm'),
        ('chan_doan_hinh_anh', 'Chẩn đoán hình ảnh'),
        ('phau_thuat', 'Phẫu thuật'),
        ('noi_khoa', 'Nội khoa'),
        ('ngoai_khoa', 'Ngoại khoa'),
        ('san_phu_khoa', 'Sản phụ khoa'),
        ('nhi_khoa', 'Nhi khoa'),
        ('rang_ham_mat', 'Răng hàm mặt'),
        ('mat', 'Mắt'),
        ('tai_mui_hong', 'Tai mũi họng'),
        ('phuc_hoi_chuc_nang', 'Phục hồi chức năng'),
        ('khac', 'Khác'),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    service_type = models.CharField(max_length=50, choices=SERVICE_TYPE_CHOICES, default='khac')
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class MedicalFacility(models.Model):
    STATUS_CHOICES = [
        ('active', 'Đang hoạt động'),
        ('paused', 'Tạm dừng'),
        ('holiday', 'Nghỉ lễ'),
        ('maintenance', 'Bảo trì'),
        ('closed', 'Ngừng hoạt động'),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    address = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    services = models.ManyToManyField(Service, blank=True, related_name='facilities')

    def __str__(self):
        return self.name


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    module = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    code = models.CharField(max_length=50, unique=True)
    facility = models.ForeignKey(MedicalFacility, on_delete=models.CASCADE, related_name="users", null=True, blank=True)
    name = models.CharField(max_length=255)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    patient = models.OneToOneField('Patient', on_delete=models.SET_NULL, null=True, blank=True, related_name='user')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    @property
    def role_code(self):
        return self.role.code if self.role else None

    def has_perm_code(self, perm_code):
        if self.role:
            return self.role.permissions.filter(code=perm_code).exists()
        return False


class PatientDocument(models.Model):
    patient = models.ForeignKey("Patient", on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to='patient_documents/')
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document for {self.patient.name}"


class Patient(models.Model):
    IDENTIFIER_CHOICES = [
        ('insurance', 'Số BHYT'),
        ('national_id', 'CMND/CCCD'),
        ('phone', 'Số điện thoại'),
    ]

    identifier_type = models.CharField(max_length=20, choices=IDENTIFIER_CHOICES)
    identifier = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    contact_info = models.TextField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    created_by_facility = models.ForeignKey(MedicalFacility, on_delete=models.SET_NULL, null=True, related_name="patients")
    activity_history = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class MedicalExamination(models.Model):
    STATUS_CHOICES = [
        ('awaiting_payment', 'Chờ thanh toán'),
        ('pending', 'Chờ khám'),
        ('in_progress', 'Đang khám'),
        ('completed', 'Hoàn thành'),
        ('cancelled', 'Đã hủy'),
    ]

    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='examinations')
    facility = models.ForeignKey('MedicalFacility', on_delete=models.CASCADE, related_name='examinations')
    doctor = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='examinations')
    examination_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='awaiting_payment')
    overall_result = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Phiếu khám {self.patient.name} - {self.examination_date.strftime("%d/%m/%Y")}'


class ExaminationService(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ thực hiện'),
        ('in_progress', 'Đang thực hiện'),
        ('completed', 'Hoàn thành'),
    ]

    examination = models.ForeignKey(MedicalExamination, on_delete=models.CASCADE, related_name='examination_services')
    service = models.ForeignKey('Service', on_delete=models.CASCADE, related_name='examination_services')
    assigned_doctor = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_examination_services')
    service_time = models.DateTimeField(null=True, blank=True)
    room = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    result = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'{self.service.name} - {self.examination}'


class ExaminationDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ('attachment', 'File đính kèm'),
        ('result', 'File kết quả'),
    ]

    examination = models.ForeignKey(MedicalExamination, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='examination_documents/')
    document_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='attachment')
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.get_document_type_display()} - {self.original_filename}'


class ExaminationServiceDocument(models.Model):
    examination_service = models.ForeignKey(ExaminationService, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='examination_service_documents/')
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.original_filename}'


class ExaminationConsult(models.Model):
    """
    Bác sĩ hội chẩn cho một phiếu khám, mỗi bác sĩ có ghi chú/kết quả hội chẩn riêng.
    """
    examination = models.ForeignKey(MedicalExamination, on_delete=models.CASCADE, related_name='consults')
    doctor = models.ForeignKey('User', on_delete=models.CASCADE, related_name='examination_consults')
    result = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('examination', 'doctor')

    def __str__(self):
        return f'Hội chẩn {self.examination_id} - {self.doctor.name}'


class DiagnosisCatalog(models.Model):
    order_number = models.IntegerField()
    exam_time = models.DateTimeField()
    patient_code = models.CharField(max_length=100)
    patient_name = models.CharField(max_length=255)
    service_type = models.CharField(max_length=255)
    facility = models.ForeignKey(MedicalFacility, on_delete=models.CASCADE, related_name="diagnoses")
    department = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    from_date = models.DateField()
    to_date = models.DateField()
    identifier = models.CharField(max_length=100)
    full_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.patient_name} - {self.exam_time.date()}"


class DiagnosisDetail(models.Model):
    diagnosis = models.ForeignKey(DiagnosisCatalog, on_delete=models.CASCADE, related_name="details")
    attachments = models.FileField(upload_to='diagnosis_attachments/', blank=True, null=True)
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    result = models.TextField()

    def __str__(self):
        return f"Diagnosis by {self.doctor}"


class DiagnosisRecord(models.Model):
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='diagnosis_records')
    service_type = models.CharField(max_length=200)
    department = models.CharField(max_length=200)
    examination_place = models.CharField(max_length=200)
    examination_time = models.DateTimeField()
    public_token = models.CharField(max_length=100, null=True, blank=True, unique=True)

    doctor = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosis_records'
    )

    diagnosis_result = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_public_token(self):
        self.public_token = uuid.uuid4().hex
        self.save()

    def __str__(self):
        return f'Chuẩn đoán {self.patient.name} ({self.examination_time.date()})'


class DiagnosisDocument(models.Model):
    diagnosis_record = models.ForeignKey(
        DiagnosisRecord,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    file = models.FileField(upload_to='diagnosis_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Document for {self.diagnosis_record.patient.name} - {self.file.name.split("/")[-1]}'
