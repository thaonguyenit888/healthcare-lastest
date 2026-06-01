from django.shortcuts import redirect, render
from django.contrib.auth import get_user_model

User = get_user_model()
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

from api.decorators import admin_required, permission_required
from api.models import (
    DiagnosisDocument, DiagnosisRecord, MedicalFacility, Patient, PatientDocument,
    Role, Permission, Service, MedicalExamination, ExaminationService,
    ExaminationDocument, ExaminationServiceDocument, ExaminationConsult
)
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_GET
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from django.utils.dateparse import parse_date

from django.contrib.auth import authenticate, login, logout as auth_logout

from datetime import datetime

import json


def accessible_examinations_for(user, queryset=None):
    if queryset is None:
        queryset = MedicalExamination.objects.all()

    if getattr(user, 'role_code', None) == 'admin':
        return queryset

    if getattr(user, 'role_code', None) == 'doctor':
        access_filter = Q(consults__doctor=user)
        if user.facility_id:
            access_filter |= Q(facility_id=user.facility_id)

        allowed_ids = (
            MedicalExamination.objects
            .filter(access_filter)
            .values('pk')
            .distinct()
        )
        return queryset.filter(pk__in=allowed_ids)

    return queryset.none()


def examination_not_found_response():
    return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)


def pending_consult_filter_for(user):
    return ExaminationConsult.objects.filter(
        Q(result__isnull=True) | Q(result=''),
        examination=OuterRef('pk'),
        doctor=user,
    )


def can_edit_examination_results(user, examination):
    if getattr(user, 'role_code', None) == 'admin':
        return True
    return getattr(user, 'role_code', None) == 'doctor' and examination.doctor_id == user.id


@admin_required
def facility_list(request):
    facilities = MedicalFacility.objects.prefetch_related('services').all()
    services = Service.objects.all().order_by('service_type', 'name')
    # Group services by type for modal display
    from itertools import groupby
    grouped_services = []
    for type_key, group in groupby(services, key=lambda s: s.service_type):
        type_label = dict(Service.SERVICE_TYPE_CHOICES).get(type_key, type_key)
        grouped_services.append({'type_key': type_key, 'type_label': type_label, 'items': list(group)})
    return render(request, 'facility_list.html', {
        'facilities': facilities,
        'grouped_services': grouped_services,
        'status_choices': MedicalFacility.STATUS_CHOICES,
        'tab': 'facilities',
    })


@admin_required
def service_list(request):
    services = Service.objects.all().order_by('service_type', 'name')
    return render(request, 'service_list.html', {
        'services': services,
        'service_type_choices': Service.SERVICE_TYPE_CHOICES,
        'tab': 'services',
    })


@permission_required('report.view')
def report_list(request):
    subtab = request.GET.get('tab', 'month')
    if subtab not in ('month', 'quarter', 'year'):
        subtab = 'month'
    context = {'tab': 'reports', 'subtab': subtab}

    if subtab in ('month', 'quarter', 'year'):
        facilities = MedicalFacility.objects.all().order_by('name')
        facility_id = request.GET.get('facility_id') or ''

        base_qs = ExaminationService.objects.select_related('examination', 'service')
        if facility_id:
            base_qs = base_qs.filter(examination__facility_id=facility_id)

        years = list(
            base_qs.annotate(y=ExtractYear('examination__examination_date'))
            .values_list('y', flat=True).distinct().order_by('y')
        )

        selected_year = request.GET.get('year')
        if not selected_year and years:
            selected_year = str(years[-1])
        elif selected_year and selected_year.isdigit() and int(selected_year) not in years:
            selected_year = str(years[-1]) if years else ''

        filtered = base_qs
        if selected_year:
            filtered = filtered.filter(examination__examination_date__year=int(selected_year))
        else:
            filtered = filtered.none()

        if subtab == 'month':
            monthly_totals = {i: 0 for i in range(1, 13)}
            monthly_amounts = {i: 0 for i in range(1, 13)}
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('m').annotate(c=Count('id')):
                if row['m']:
                    monthly_totals[row['m']] = row['c']
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('m').annotate(total=Sum('price')):
                if row['m']:
                    monthly_amounts[row['m']] = int(row['total'] or 0)

            service_map = {}
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('service_id', 'service__name', 'm').annotate(c=Count('id')):
                if not row['m']:
                    continue
                sid = row['service_id']
                if sid not in service_map:
                    service_map[sid] = {
                        'name': row['service__name'],
                        'months': {i: 0 for i in range(1, 13)}
                    }
                service_map[sid]['months'][row['m']] = row['c']

            service_rows = []
            for sid, info in service_map.items():
                service_rows.append({
                    'name': info['name'],
                    'months': [info['months'][i] for i in range(1, 13)]
                })
            service_rows.sort(key=lambda x: x['name'])

            context.update({
                'facilities': facilities,
                'selected_facility_id': str(facility_id),
                'years': years,
                'selected_year': selected_year or '',
                'chart_labels_json': json.dumps([f'T{i}' for i in range(1, 13)]),
                'chart_values_json': json.dumps([monthly_totals[i] for i in range(1, 13)]),
                'chart_amounts_json': json.dumps([monthly_amounts[i] for i in range(1, 13)]),
                'service_rows': service_rows,
            })
        elif subtab == 'quarter':
            quarter_totals = {i: 0 for i in range(1, 5)}
            quarter_amounts = {i: 0 for i in range(1, 5)}
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('m').annotate(c=Count('id')):
                if row['m']:
                    q = (row['m'] - 1) // 3 + 1
                    quarter_totals[q] += row['c']
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('m').annotate(total=Sum('price')):
                if row['m']:
                    q = (row['m'] - 1) // 3 + 1
                    quarter_amounts[q] += int(row['total'] or 0)

            service_map = {}
            for row in filtered.annotate(m=ExtractMonth('examination__examination_date')).values('service_id', 'service__name', 'm').annotate(c=Count('id')):
                if not row['m']:
                    continue
                sid = row['service_id']
                if sid not in service_map:
                    service_map[sid] = {
                        'name': row['service__name'],
                        'quarters': {i: 0 for i in range(1, 5)}
                    }
                q = (row['m'] - 1) // 3 + 1
                service_map[sid]['quarters'][q] += row['c']

            service_rows = []
            for sid, info in service_map.items():
                service_rows.append({
                    'name': info['name'],
                    'quarters': [info['quarters'][i] for i in range(1, 5)]
                })
            service_rows.sort(key=lambda x: x['name'])

            context.update({
                'facilities': facilities,
                'selected_facility_id': str(facility_id),
                'years': years,
                'selected_year': selected_year or '',
                'chart_labels_json': json.dumps([f'Q{i}' for i in range(1, 5)]),
                'chart_values_json': json.dumps([quarter_totals[i] for i in range(1, 5)]),
                'chart_amounts_json': json.dumps([quarter_amounts[i] for i in range(1, 5)]),
                'service_rows': service_rows,
            })
        else:
            year_totals = {int(y): 0 for y in years}
            year_amounts = {int(y): 0 for y in years}

            for row in base_qs.annotate(y=ExtractYear('examination__examination_date')).values('y').annotate(c=Count('id')):
                if row['y']:
                    year_totals[int(row['y'])] = row['c']
            for row in base_qs.annotate(y=ExtractYear('examination__examination_date')).values('y').annotate(total=Sum('price')):
                if row['y']:
                    year_amounts[int(row['y'])] = int(row['total'] or 0)

            service_map = {}
            for row in base_qs.annotate(y=ExtractYear('examination__examination_date')).values('service_id', 'service__name', 'y').annotate(c=Count('id')):
                if not row['y']:
                    continue
                sid = row['service_id']
                if sid not in service_map:
                    service_map[sid] = {
                        'name': row['service__name'],
                        'years': {int(y): 0 for y in years}
                    }
                service_map[sid]['years'][int(row['y'])] = row['c']

            service_rows = []
            for sid, info in service_map.items():
                service_rows.append({
                    'name': info['name'],
                    'years': [info['years'][int(y)] for y in years]
                })
            service_rows.sort(key=lambda x: x['name'])

            context.update({
                'facilities': facilities,
                'selected_facility_id': str(facility_id),
                'years': years,
                'chart_labels_json': json.dumps([str(y) for y in years]),
                'chart_values_json': json.dumps([year_totals[int(y)] for y in years]),
                'chart_amounts_json': json.dumps([year_amounts[int(y)] for y in years]),
                'service_rows': service_rows,
            })

    return render(request, 'report_list.html', context)


@admin_required
def user_list(request):
    users = User.objects.select_related('facility', 'role', 'patient').all()
    facilities = MedicalFacility.objects.all()
    roles = Role.objects.all()
    patients = Patient.objects.select_related('user').order_by('identifier')
    patient_role = Role.objects.filter(code='patient').first()
    return render(request, 'user_list.html', {
        'users': users,
        'tab': 'users',
        'subtab': 'users',
        'facilities': facilities,
        'roles': roles,
        'patients': patients,
        'patient_role_id': patient_role.id if patient_role else '',
    })


@admin_required
def role_list(request):
    roles = Role.objects.prefetch_related('permissions').all()
    permissions = Permission.objects.all()
    return render(request, 'role_list.html', {
        'roles': roles,
        'permissions': permissions,
        'tab': 'users',
        'subtab': 'roles',
    })


@admin_required
def permission_list(request):
    permissions = Permission.objects.all()
    modules = Permission.objects.values_list('module', flat=True).distinct()
    return render(request, 'permission_list.html', {
        'permissions': permissions,
        'modules': list(modules),
        'tab': 'users',
        'subtab': 'permissions',
    })


@permission_required('patient.view')
def patient_list(request):
    if request.user.role_code == 'admin':
        patients = Patient.objects.all()
        facilities = MedicalFacility.objects.all()
    else:
        patients = Patient.objects.filter(created_by_facility=request.user.facility)
        facilities = MedicalFacility.objects.filter(id=request.user.facility_id)
    return render(request, 'patient_list.html', {
        'patients': patients,
        'tab': 'patients',
        'facilities': facilities,
    })


@permission_required('examination.view')
def examination_list(request):
    examinations = accessible_examinations_for(request.user, MedicalExamination.objects.select_related(
        'patient', 'facility', 'doctor'
    )).prefetch_related('examination_services__service').annotate(
        total_price=Sum('examination_services__price')
    ).order_by('-examination_date')
    if request.user.role_code == 'doctor':
        examinations = examinations.annotate(
            has_pending_consult=Exists(pending_consult_filter_for(request.user))
        )

    patients = Patient.objects.all()
    facilities = MedicalFacility.objects.prefetch_related('services').filter(status='active')
    if request.user.role_code == 'doctor':
        accessible_facility_ids = accessible_examinations_for(request.user).values_list('facility_id', flat=True)
        facility_filter = Q(pk__in=accessible_facility_ids)
        if request.user.facility_id:
            facility_filter |= Q(pk=request.user.facility_id)
        facilities = facilities.filter(facility_filter).distinct()

    doctors = User.objects.filter(role__code='doctor')
    return render(request, 'examination_list.html', {
        'examinations': examinations,
        'patients': patients,
        'facilities': facilities,
        'doctors': doctors,
        'status_choices': MedicalExamination.STATUS_CHOICES,
        'tab': 'examinations',
    })


@permission_required('examination.view')
def examination_detail(request, pk):
    try:
        exam = accessible_examinations_for(
            request.user,
            MedicalExamination.objects.select_related('patient', 'facility', 'doctor')
        ).get(pk=pk)
    except MedicalExamination.DoesNotExist:
        return examination_not_found_response()

    services = ExaminationService.objects.filter(examination=exam).select_related(
        'service', 'assigned_doctor'
    ).prefetch_related('documents')
    overall_docs = ExaminationDocument.objects.filter(examination=exam)
    consults = ExaminationConsult.objects.filter(examination=exam).select_related('doctor')
    has_pending_consult = (
        request.user.role_code == 'doctor'
        and consults.filter(doctor=request.user).filter(Q(result__isnull=True) | Q(result='')).exists()
    )
    can_edit_results = can_edit_examination_results(request.user, exam)
    doctors = User.objects.filter(role__code='doctor')
    return render(request, 'examination_detail.html', {
        'examination': exam,
        'services': services,
        'overall_docs': overall_docs,
        'consults': consults,
        'has_pending_consult': has_pending_consult,
        'can_edit_results': can_edit_results,
        'doctors': doctors,
        'tab': 'examinations',
    })


@csrf_exempt
@permission_required('examination.view')
def get_examination(request, pk):
    try:
        exam = accessible_examinations_for(
            request.user,
            MedicalExamination.objects.select_related('patient', 'facility', 'doctor')
        ).get(pk=pk)
        services = ExaminationService.objects.filter(examination=exam).select_related('service', 'assigned_doctor')
        exam_docs = ExaminationDocument.objects.filter(examination=exam)

        services_data = []
        for s in services:
            svc_docs = ExaminationServiceDocument.objects.filter(examination_service=s)
            services_data.append({
                'id': s.id,
                'service_id': s.service.id,
                'service_name': s.service.name,
                'room': s.room or '',
                'assigned_doctor_id': s.assigned_doctor.id if s.assigned_doctor else '',
                'assigned_doctor_name': s.assigned_doctor.name if s.assigned_doctor else '',
                'price': int(s.price),
                'result': s.result or '',
                'status': s.status,
                'notes': s.notes or '',
                'documents': [{'id': d.id, 'file_url': d.file.url, 'file_name': d.original_filename or d.file.name.split('/')[-1]} for d in svc_docs],
            })

        consults = ExaminationConsult.objects.filter(examination=exam).select_related('doctor')

        data = {
            'id': exam.id,
            'patient_id': exam.patient.id,
            'patient_name': exam.patient.name,
            'facility_id': exam.facility.id,
            'facility_name': exam.facility.name,
            'doctor_id': exam.doctor.id if exam.doctor else '',
            'doctor_name': exam.doctor.name if exam.doctor else '',
            'examination_date': exam.examination_date.strftime('%Y-%m-%dT%H:%M'),
            'status': exam.status,
            'overall_result': exam.overall_result or '',
            'notes': exam.notes or '',
            'services': services_data,
            'consult_doctors': [c.doctor_id for c in consults],
            'documents': [{'id': d.id, 'file_url': d.file.url, 'file_name': d.original_filename or d.file.name.split('/')[-1], 'document_type': d.document_type} for d in exam_docs],
        }
        return JsonResponse(data)
    except MedicalExamination.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)


@csrf_exempt
@transaction.atomic
@permission_required('examination.create')
def create_examination(request):
    if request.method == 'POST':
        try:
            patient_id = request.POST['patient_id']
            facility_id = request.POST['facility_id']
            if request.user.role_code == 'doctor' and str(request.user.facility_id or '') != str(facility_id):
                return JsonResponse({'error': 'Không được phép tạo phiếu khám ngoài cơ sở trực thuộc'}, status=403)

            doctor_id = request.POST.get('doctor_id')
            examination_date = request.POST['examination_date']
            status = request.POST.get('status', 'awaiting_payment')
            overall_result = request.POST.get('overall_result', '')
            notes = request.POST.get('notes', '')

            exam = MedicalExamination.objects.create(
                patient_id=patient_id,
                facility_id=facility_id,
                doctor_id=doctor_id if doctor_id else None,
                examination_date=examination_date,
                status=status,
                overall_result=overall_result,
                notes=notes,
            )

            # Consult doctors (JSON array of ids)
            consult_json = request.POST.get('consult_doctors', '[]')
            consult_ids = json.loads(consult_json)
            for doc_id in consult_ids:
                ExaminationConsult.objects.get_or_create(examination=exam, doctor_id=doc_id)

            # Services (JSON array)
            services_json = request.POST.get('services', '[]')
            services_list = json.loads(services_json)
            for svc in services_list:
                svc_price = svc.get('price', 0) or 0
                if not svc_price:
                    try:
                        svc_price = Service.objects.get(pk=svc['service_id']).price
                    except Service.DoesNotExist:
                        svc_price = 0
                ExaminationService.objects.create(
                    examination=exam,
                    service_id=svc['service_id'],
                    assigned_doctor_id=svc.get('assigned_doctor_id') or None,
                    price=svc_price,
                    result=svc.get('result', ''),
                    status=svc.get('status', 'pending'),
                    notes=svc.get('notes', ''),
                )

            # General documents
            for f in request.FILES.getlist('documents'):
                ExaminationDocument.objects.create(
                    examination=exam, file=f, document_type='attachment',
                    original_filename=f.name,
                )
            for f in request.FILES.getlist('result_documents'):
                ExaminationDocument.objects.create(
                    examination=exam, file=f, document_type='result',
                    original_filename=f.name,
                )

            return JsonResponse({'message': 'Tạo phiếu khám thành công', 'id': exam.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@transaction.atomic
@permission_required('examination.edit')
def update_examination(request, pk):
    if request.method == 'POST':
        try:
            exam = accessible_examinations_for(request.user).get(pk=pk)
            if request.user.role_code == 'doctor' and str(exam.facility_id) != str(request.POST['facility_id']):
                return JsonResponse({'error': 'Không được phép chuyển phiếu khám sang cơ sở khác'}, status=403)

            exam.patient_id = request.POST['patient_id']
            exam.facility_id = request.POST['facility_id']
            doctor_id = request.POST.get('doctor_id')
            exam.doctor_id = doctor_id if doctor_id else None
            exam.examination_date = request.POST['examination_date']
            exam.status = request.POST.get('status', exam.status)
            exam.overall_result = request.POST.get('overall_result', '')
            exam.notes = request.POST.get('notes', '')
            exam.save()

            # Update consult doctors list
            consult_json = request.POST.get('consult_doctors', '[]')
            consult_ids = set(json.loads(consult_json))
            existing_consults = ExaminationConsult.objects.filter(examination=exam)
            existing_ids = set(existing_consults.values_list('doctor_id', flat=True))

            # Remove doctors no longer in list
            existing_consults.filter(doctor_id__in=(existing_ids - consult_ids)).delete()
            # Add new doctors
            for doc_id in (consult_ids - existing_ids):
                ExaminationConsult.objects.create(examination=exam, doctor_id=doc_id)

            # Update services: keep existing, add new, remove unchecked
            services_json = request.POST.get('services', '[]')
            services_list = json.loads(services_json)
            new_service_ids = {int(svc['service_id']) for svc in services_list}
            existing_service_ids = set(exam.examination_services.values_list('service_id', flat=True))

            # Remove services that were unchecked
            exam.examination_services.filter(service_id__in=existing_service_ids - new_service_ids).delete()

            # Add new services (not already existing)
            for svc in services_list:
                sid = int(svc['service_id'])
                if sid not in existing_service_ids:
                    svc_price = svc.get('price', 0) or 0
                    if not svc_price:
                        try:
                            svc_price = Service.objects.get(pk=sid).price
                        except Service.DoesNotExist:
                            svc_price = 0
                    ExaminationService.objects.create(
                        examination=exam,
                        service_id=sid,
                        price=svc_price,
                    )

            # Delete selected docs
            delete_doc_ids = request.POST.get('delete_documents', '')
            if delete_doc_ids:
                ids = [int(i) for i in delete_doc_ids.split(',') if i.strip().isdigit()]
                ExaminationDocument.objects.filter(id__in=ids, examination=exam).delete()

            # New documents
            for f in request.FILES.getlist('documents'):
                ExaminationDocument.objects.create(
                    examination=exam, file=f, document_type='attachment',
                    original_filename=f.name,
                )
            for f in request.FILES.getlist('result_documents'):
                ExaminationDocument.objects.create(
                    examination=exam, file=f, document_type='result',
                    original_filename=f.name,
                )

            return JsonResponse({'message': 'Cập nhật phiếu khám thành công'})
        except MedicalExamination.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('examination.delete')
def delete_examination(request, pk):
    if request.method == 'POST':
        try:
            exam = accessible_examinations_for(request.user).get(pk=pk)
            exam.delete()
            return JsonResponse({'message': 'Xóa phiếu khám thành công'})
        except MedicalExamination.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def get_facility_services_api(request, pk):
    """Get services available at a facility"""
    try:
        facility = MedicalFacility.objects.prefetch_related('services').get(pk=pk)
        services = [{'id': s.id, 'name': s.name, 'service_type': s.get_service_type_display(), 'price': int(s.price)} for s in facility.services.all()]
        return JsonResponse({'services': services})
    except MedicalFacility.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy cơ sở'}, status=404)


@csrf_exempt
@transaction.atomic
@permission_required('examination.edit')
def update_examination_service(request, pk):
    """Update a single examination service (result, doctor, files, etc.)"""
    if request.method == 'POST':
        try:
            svc = ExaminationService.objects.select_related('examination').get(pk=pk)
            if not accessible_examinations_for(request.user).filter(pk=svc.examination_id).exists():
                return examination_not_found_response()
            if not can_edit_examination_results(request.user, svc.examination):
                return JsonResponse({'error': 'Không được phép cập nhật dịch vụ khám của phiếu này'}, status=403)

            svc.assigned_doctor_id = request.POST.get('assigned_doctor_id') or None
            service_time = request.POST.get('service_time')
            svc.service_time = service_time if service_time else None
            svc.price = request.POST.get('price', svc.price) or 0
            svc.status = request.POST.get('status', svc.status)
            svc.result = request.POST.get('result', '')
            svc.notes = request.POST.get('notes', '')
            svc.room = request.POST.get('room', '').strip() or None
            svc.save()

            # Delete selected docs
            delete_doc_ids = request.POST.get('delete_documents', '')
            if delete_doc_ids:
                ids = [int(i) for i in delete_doc_ids.split(',') if i.strip().isdigit()]
                ExaminationServiceDocument.objects.filter(id__in=ids, examination_service=svc).delete()

            # New files
            for f in request.FILES.getlist('documents'):
                ExaminationServiceDocument.objects.create(
                    examination_service=svc, file=f, original_filename=f.name,
                )

            return JsonResponse({'message': 'Cập nhật dịch vụ thành công'})
        except ExaminationService.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy dịch vụ'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@transaction.atomic
@permission_required('examination.edit')
def update_examination_overall(request, pk):
    """Update overall result + upload general documents"""
    if request.method == 'POST':
        try:
            exam = accessible_examinations_for(request.user).get(pk=pk)
            if not can_edit_examination_results(request.user, exam):
                return JsonResponse({'error': 'Không được phép sửa kết quả khám tổng'}, status=403)
            exam.overall_result = request.POST.get('overall_result', '')
            exam.save()

            for f in request.FILES.getlist('documents'):
                ExaminationDocument.objects.create(
                    examination=exam, file=f, document_type='attachment',
                    original_filename=f.name,
                )

            return JsonResponse({'message': 'Cập nhật kết quả tổng thành công'})
        except MedicalExamination.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('examination.edit')
def update_examination_status(request, pk):
    """Update examination status only"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            exam = accessible_examinations_for(request.user).get(pk=pk)
            if not can_edit_examination_results(request.user, exam):
                return JsonResponse({'error': 'Không được phép cập nhật trạng thái phiếu khám'}, status=403)
            exam.status = data['status']
            exam.save()
            return JsonResponse({'message': 'Cập nhật trạng thái thành công'})
        except MedicalExamination.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy phiếu khám'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('examination.edit')
def delete_examination_doc(request, pk):
    """Delete an examination document"""
    if request.method == 'POST':
        try:
            doc = ExaminationDocument.objects.select_related('examination').get(pk=pk)
            if not accessible_examinations_for(request.user).filter(pk=doc.examination_id).exists():
                return examination_not_found_response()
            if not can_edit_examination_results(request.user, doc.examination):
                return JsonResponse({'error': 'Không được phép xóa tài liệu của phiếu này'}, status=403)

            doc.delete()
            return JsonResponse({'message': 'Đã xóa'})
        except ExaminationDocument.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('examination.edit')
def update_examination_consult(request, pk):
    """
    Cập nhật kết quả hội chẩn của một bác sĩ cho phiếu khám.
    - Chỉ cho phép: chính bác sĩ đó hoặc admin.
    """
    if request.method == 'POST':
        try:
            consult = ExaminationConsult.objects.select_related('doctor', 'examination').get(pk=pk)
            user = request.user
            if not accessible_examinations_for(user).filter(pk=consult.examination_id).exists():
                return examination_not_found_response()

            if user.role_code != 'admin' and consult.doctor_id != user.id:
                return JsonResponse({'error': 'Không được phép sửa kết quả của bác sĩ khác'}, status=403)

            consult.result = request.POST.get('result', '')
            consult.save()
            return JsonResponse({'message': 'Cập nhật kết quả hội chẩn thành công'})
        except ExaminationConsult.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy bản ghi hội chẩn'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@login_required
def dashboard(request):
    if request.user.role_code in ('admin', 'doctor'):
        return render(request, 'dashboard_home.html', {'tab': 'home'})
    elif request.user.role_code == 'patient':
        return redirect('patient_dashboard')
    else:
        return redirect('logout')


@login_required
def patient_lookup_api(request):
    identifier = request.GET.get('identifier', '').strip()
    if not identifier:
        return JsonResponse({'error': 'Thiếu số định danh'}, status=400)

    patients = Patient.objects.filter(identifier=identifier)
    if not patients.exists():
        return JsonResponse({'data': [], 'patient_name': ''})

    patient = patients.first()
    records = DiagnosisRecord.objects.filter(patient=patient).select_related('doctor').order_by('-examination_time')

    data = []
    for r in records:
        public_url = None
        if r.public_token:
            public_url = f'/diagnosis/public/{r.public_token}/'
        data.append({
            'examination_time': r.examination_time.strftime('%d/%m/%Y %H:%M'),
            'service_type': r.service_type,
            'department': r.department,
            'examination_place': r.examination_place,
            'doctor_name': r.doctor.name if r.doctor else '',
            'diagnosis_result': r.diagnosis_result,
            'public_url': public_url,
        })

    return JsonResponse({'data': data, 'patient_name': patient.name})


@login_required
def patient_lookup_patients_api(request):
    facility_id = request.GET.get('facility_id')
    qs = Patient.objects.all().order_by('identifier', 'name')
    if facility_id:
        qs = qs.filter(examinations__facility_id=facility_id).distinct()
    data = [{'id': p.id, 'name': p.name, 'identifier': p.identifier} for p in qs]
    return JsonResponse({'data': data})


@login_required
def patient_lookup_exams_api(request):
    facility_id = request.GET.get('facility_id')
    patient_id = request.GET.get('patient_id')
    exam_year = request.GET.get('exam_year')
    exam_month = request.GET.get('exam_month')

    qs = MedicalExamination.objects.select_related('facility', 'doctor', 'patient')
    if facility_id:
        qs = qs.filter(facility_id=facility_id)
    if patient_id:
        qs = qs.filter(patient_id=patient_id)
    if exam_year and exam_year.isdigit():
        qs = qs.filter(examination_date__year=int(exam_year))
        if exam_month and exam_month.isdigit():
            qs = qs.filter(examination_date__month=int(exam_month))

    qs = qs.order_by('-examination_date')
    status_map = dict(MedicalExamination.STATUS_CHOICES)

    data = []
    for e in qs:
        data.append({
            'id': e.id,
            'examination_time': e.examination_date.strftime('%d/%m/%Y %H:%M'),
            'patient_name': e.patient.name if e.patient else '',
            'identifier': e.patient.identifier if e.patient else '',
            'facility_name': e.facility.name if e.facility else '',
            'doctor_name': e.doctor.name if e.doctor else '',
            'status': status_map.get(e.status, e.status),
            'overall_result': e.overall_result or '',
        })

    return JsonResponse({'data': data})


def patient_login_view(request):
    if request.user.is_authenticated:
        if request.user.role_code == 'patient':
            return redirect('patient_my_results')
        return redirect('patient_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.role_code == 'patient':
                return redirect('patient_my_results')
            return redirect('patient_dashboard')
        else:
            return render(request, 'patient_login.html', {'error': 'Tài khoản hoặc mật khẩu không đúng.'})
    return render(request, 'patient_login.html')


def patient_logout_view(request):
    auth_logout(request)
    return redirect('patient_login')


def patient_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('patient_login')
    facilities = MedicalFacility.objects.filter(examinations__isnull=False).distinct().order_by('name')
    patients = Patient.objects.none()
    years = list(
        MedicalExamination.objects.annotate(y=ExtractYear('examination_date'))
        .values_list('y', flat=True).distinct().order_by('y')
    )
    return render(request, 'patient_lookup.html', {
        'tab': 'lookup',
        'facilities': facilities,
        'patients': patients,
        'years': years,
    })


def patient_my_results(request):
    if not request.user.is_authenticated:
        return redirect('patient_login')

    patient = getattr(request.user, 'patient', None)
    if not patient:
        identifiers = [request.user.username, request.user.code]
        identifiers = [i for i in identifiers if i]
        patient = Patient.objects.filter(identifier__in=identifiers).first() if identifiers else None

    examinations = []
    if patient:
        examinations = MedicalExamination.objects.filter(patient=patient).select_related(
            'facility', 'doctor'
        ).order_by('-examination_date')

    return render(request, 'patient_my_results.html', {
        'tab': 'my_results',
        'patient': patient,
        'examinations': examinations,
    })


def patient_my_result_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect('patient_login')

    patient = getattr(request.user, 'patient', None)
    if not patient:
        identifiers = [request.user.username, request.user.code]
        identifiers = [i for i in identifiers if i]
        patient = Patient.objects.filter(identifier__in=identifiers).first() if identifiers else None

    exam = MedicalExamination.objects.select_related(
        'patient', 'facility', 'doctor'
    ).get(pk=pk)

    if not patient or exam.patient_id != patient.id:
        return redirect('patient_my_results')

    services = ExaminationService.objects.filter(examination=exam).select_related(
        'service', 'assigned_doctor'
    ).prefetch_related('documents')
    overall_docs = ExaminationDocument.objects.filter(examination=exam)
    consults = ExaminationConsult.objects.filter(examination=exam).select_related('doctor')

    return render(request, 'patient_exam_detail.html', {
        'tab': 'my_results',
        'examination': exam,
        'services': services,
        'overall_docs': overall_docs,
        'consults': consults,
    })


def patient_lookup_result_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect('patient_login')

    exam = MedicalExamination.objects.select_related(
        'patient', 'facility', 'doctor'
    ).get(pk=pk)

    if request.user.role_code == 'patient':
        patient = getattr(request.user, 'patient', None)
        if not patient:
            identifiers = [request.user.username, request.user.code]
            identifiers = [i for i in identifiers if i]
            patient = Patient.objects.filter(identifier__in=identifiers).first() if identifiers else None
        if not patient or exam.patient_id != patient.id:
            return redirect('patient_dashboard')

    services = ExaminationService.objects.filter(examination=exam).select_related(
        'service', 'assigned_doctor'
    ).prefetch_related('documents')
    overall_docs = ExaminationDocument.objects.filter(examination=exam)
    consults = ExaminationConsult.objects.filter(examination=exam).select_related('doctor')

    return render(request, 'patient_lookup_detail.html', {
        'tab': 'lookup',
        'examination': exam,
        'services': services,
        'overall_docs': overall_docs,
        'consults': consults,
    })


@csrf_exempt
def create_facility(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            facility = MedicalFacility.objects.create(
                code=data['code'],
                name=data['name'],
                address=data['address'],
                status=data.get('status', 'active'),
            )
            return JsonResponse({'message': 'Tạo thành công', 'id': facility.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def update_facility(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            facility = MedicalFacility.objects.get(pk=pk)
            facility.code = data['code']
            facility.name = data['name']
            facility.address = data['address']
            facility.status = data.get('status', facility.status)
            facility.save()
            return JsonResponse({'message': 'Cập nhật thành công'})
        except MedicalFacility.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def delete_facility(request, pk):
    if request.method == 'POST':
        try:
            facility = MedicalFacility.objects.get(pk=pk)
            facility.delete()
            return JsonResponse({'message': 'Đã xóa thành công'})
        except MedicalFacility.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def get_facility(request, pk):
    try:
        f = MedicalFacility.objects.prefetch_related('services').get(pk=pk)
        return JsonResponse({
            'id': f.id, 'code': f.code, 'name': f.name,
            'address': f.address, 'status': f.status,
            'services': list(f.services.values_list('id', flat=True)),
        })
    except MedicalFacility.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy'}, status=404)


@csrf_exempt
def update_facility_services(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            facility = MedicalFacility.objects.get(pk=pk)
            service_ids = data.get('services', [])
            facility.services.set(service_ids)
            return JsonResponse({'message': 'Cập nhật dịch vụ thành công'})
        except MedicalFacility.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def create_service(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            service = Service.objects.create(
                code=data['code'],
                name=data['name'],
                service_type=data.get('service_type', 'khac'),
                price=data.get('price', 0),
                description=data.get('description', ''),
            )
            return JsonResponse({'message': 'Tạo thành công', 'id': service.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def update_service(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            service = Service.objects.get(pk=pk)
            service.code = data['code']
            service.name = data['name']
            service.service_type = data.get('service_type', service.service_type)
            service.price = data.get('price', service.price) or 0
            service.description = data.get('description', '')
            service.save()
            return JsonResponse({'message': 'Cập nhật thành công'})
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def delete_service(request, pk):
    if request.method == 'POST':
        try:
            service = Service.objects.get(pk=pk)
            service.delete()
            return JsonResponse({'message': 'Đã xóa thành công'})
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy'}, status=404)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def create_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = Role.objects.get(pk=data['role']) if data.get('role') else None
            patient = None
            if role and role.code == 'patient':
                patient_id = data.get('patient') or user.patient_id
                if not patient_id:
                    return JsonResponse({'error': 'Vui lòng chọn bệnh nhân cho tài khoản này.'}, status=400)
                patient = Patient.objects.get(pk=patient_id)
                if User.objects.filter(patient=patient).exists():
                    return JsonResponse({'error': 'Bệnh nhân này đã có tài khoản.'}, status=400)
            user = User(
                code=data['code'],
                username=data['username'],
                name=patient.name if patient else data['name'],
                role=role,
                facility=MedicalFacility.objects.get(pk=data['facility']) if data.get('facility') else None,
                password=make_password(data['password']),
                patient=patient,
            )
            user.save()
            return JsonResponse({'message': 'Tạo người dùng thành công', 'id': user.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def update_user(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = User.objects.get(pk=pk)
            user.code = data['code']
            user.username = data['username']
            user.role = Role.objects.get(pk=data['role']) if data.get('role') else None
            patient = None
            if user.role and user.role.code == 'patient':
                patient_id = data.get('patient') or user.patient_id
                if not patient_id:
                    return JsonResponse({'error': 'Vui lòng chọn bệnh nhân cho tài khoản này.'}, status=400)
                patient = Patient.objects.get(pk=patient_id)
                if User.objects.filter(patient=patient).exclude(pk=user.pk).exists():
                    return JsonResponse({'error': 'Bệnh nhân này đã có tài khoản.'}, status=400)
            user.patient = patient
            user.name = patient.name if patient else data['name']
            user.facility = MedicalFacility.objects.get(pk=data['facility']) if data.get('facility') else None
            if data.get('password'):
                user.password = make_password(data['password'])
            user.save()
            return JsonResponse({'message': 'Cập nhật người dùng thành công'})
        except User.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy người dùng'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def delete_user(request, pk):
    if request.method == 'POST':
        try:
            user = User.objects.get(pk=pk)
            user.delete()
            return JsonResponse({'message': 'Đã xóa thành công'})
        except User.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy người dùng'}, status=404)
    return HttpResponseBadRequest("Invalid method")


# ===== Role CRUD =====

@csrf_exempt
def create_role(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = Role.objects.create(
                code=data['code'],
                name=data['name'],
                description=data.get('description', '')
            )
            perm_ids = data.get('permissions', [])
            if perm_ids:
                role.permissions.set(perm_ids)
            return JsonResponse({'message': 'Tạo vai trò thành công', 'id': role.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def update_role(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = Role.objects.get(pk=pk)
            role.code = data['code']
            role.name = data['name']
            role.description = data.get('description', '')
            role.save()
            perm_ids = data.get('permissions', [])
            role.permissions.set(perm_ids)
            return JsonResponse({'message': 'Cập nhật vai trò thành công'})
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy vai trò'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def delete_role(request, pk):
    if request.method == 'POST':
        try:
            role = Role.objects.get(pk=pk)
            role.delete()
            return JsonResponse({'message': 'Xóa vai trò thành công'})
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy vai trò'}, status=404)
    return HttpResponseBadRequest("Invalid method")


def get_role(request, pk):
    try:
        role = Role.objects.prefetch_related('permissions').get(pk=pk)
        data = {
            'id': role.id,
            'code': role.code,
            'name': role.name,
            'description': role.description or '',
            'permissions': list(role.permissions.values_list('id', flat=True)),
        }
        return JsonResponse(data)
    except Role.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy vai trò'}, status=404)


# ===== Permission CRUD =====

@csrf_exempt
def create_permission(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            perm = Permission.objects.create(
                code=data['code'],
                name=data['name'],
                module=data['module'],
                description=data.get('description', '')
            )
            return JsonResponse({'message': 'Tạo quyền thành công', 'id': perm.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def update_permission(request, pk):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            perm = Permission.objects.get(pk=pk)
            perm.code = data['code']
            perm.name = data['name']
            perm.module = data['module']
            perm.description = data.get('description', '')
            perm.save()
            return JsonResponse({'message': 'Cập nhật quyền thành công'})
        except Permission.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy quyền'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
def delete_permission(request, pk):
    if request.method == 'POST':
        try:
            perm = Permission.objects.get(pk=pk)
            perm.delete()
            return JsonResponse({'message': 'Xóa quyền thành công'})
        except Permission.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy quyền'}, status=404)
    return HttpResponseBadRequest("Invalid method")


# ===== Existing views (unchanged logic) =====

@csrf_exempt
@permission_required('patient.create')
def create_patient(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                identifier_type = request.POST['identifier_type']
                identifier = request.POST['identifier']
                name = request.POST['name']
                contact_info = request.POST.get('contact_info')
                gender = request.POST['gender']
                facility_id = request.POST.get('facility_id')

                patient = Patient.objects.create(
                    identifier_type=identifier_type,
                    identifier=identifier,
                    name=name,
                    contact_info=contact_info,
                    gender=gender,
                    created_by_facility_id=facility_id if facility_id else None
                )

                for file in request.FILES.getlist('documents'):
                    PatientDocument.objects.create(patient=patient, file=file, original_filename=file.name)

                return JsonResponse({'message': 'Tạo bệnh nhân thành công', 'id': patient.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('patient.edit')
def update_patient(request, pk):
    if request.method == 'POST':
        try:
            patient = Patient.objects.get(pk=pk)

            patient.identifier_type = request.POST['identifier_type']
            patient.identifier = request.POST['identifier']
            patient.name = request.POST['name']
            patient.contact_info = request.POST.get('contact_info')
            patient.gender = request.POST['gender']
            patient.created_by_facility_id = request.POST.get('facility_id') or None
            patient.save()

            for file in request.FILES.getlist('documents'):
                PatientDocument.objects.create(patient=patient, file=file, original_filename=file.name)
            delete_docs_ids = request.POST.get('delete_documents', '')
            if delete_docs_ids:
                delete_ids = [int(i) for i in delete_docs_ids.split(',') if i.strip().isdigit()]
                PatientDocument.objects.filter(id__in=delete_ids, patient=patient).delete()

            return JsonResponse({'message': 'Cập nhật thành công'})
        except Patient.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy bệnh nhân'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('patient.delete')
def delete_patient(request, pk):
    if request.method == 'POST':
        try:
            patient = Patient.objects.get(pk=pk)
            patient.delete()
            return JsonResponse({'message': 'Xóa thành công'})
        except Patient.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy bệnh nhân'}, status=404)
    return HttpResponseBadRequest("Invalid method")


@csrf_exempt
@permission_required('patient.view')
def get_patient(request, pk):
    if request.method == 'GET':
        try:
            patient = Patient.objects.get(pk=pk)
            data = {
                'id': patient.id,
                'identifier_type': patient.identifier_type,
                'identifier': patient.identifier,
                'name': patient.name,
                'contact_info': patient.contact_info,
                'gender': patient.gender,
                'created_by_facility': patient.created_by_facility.id if patient.created_by_facility else None,
                'documents': [{"file_url": doc.file.url, "id": doc.id, "file_name": doc.original_filename} for doc in patient.documents.all()]
            }
            return JsonResponse(data)
        except Patient.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy bệnh nhân'}, status=404)

    return HttpResponseBadRequest("Invalid method")


@permission_required('diagnosis.view')
def diagnosis_list(request):
    diagnosis_records = DiagnosisRecord.objects.all().select_related('doctor')
    facilities = MedicalFacility.objects.all()
    doctors = User.objects.filter(role__code='doctor')
    patients = Patient.objects.all()
    return render(request, 'diagnosis_list.html', {
        'diagnosis_records': diagnosis_records,
        'facilities': facilities,
        'doctors': doctors,
        'patients': patients,
        'tab': 'diagnosis'
    })


@csrf_exempt
@transaction.atomic
@permission_required('diagnosis.create')
def create_diagnosis(request):
    if request.method == 'POST':
        try:
            patient_id = request.POST['patient_id']
            service_type = request.POST['service_type']
            department = request.POST['department']
            examination_place = request.POST['examination_place']
            examination_time = request.POST['examination_time']
            diagnosis_result = request.POST['diagnosis_result']
            doctor_id = request.POST.get('doctor_id')

            diagnosis = DiagnosisRecord.objects.create(
                patient=Patient.objects.get(id=patient_id),
                service_type=service_type,
                department=department,
                examination_place=examination_place,
                examination_time=examination_time,
                diagnosis_result=diagnosis_result,
                doctor=User.objects.get(pk=doctor_id) if doctor_id else None
            )

            for file in request.FILES.getlist('documents'):
                DiagnosisDocument.objects.create(diagnosis_record=diagnosis, file=file)

            return JsonResponse({'message': 'Tạo chuẩn đoán thành công', 'id': diagnosis.id})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@transaction.atomic
@permission_required('diagnosis.edit')
def update_diagnosis(request, id):
    if request.method == 'POST':
        try:
            diagnosis = DiagnosisRecord.objects.get(id=id)

            diagnosis.service_type = request.POST['service_type']
            diagnosis.department = request.POST['department']
            diagnosis.examination_place = request.POST['examination_place']
            diagnosis.diagnosis_result = request.POST['diagnosis_result']
            doctor_id = request.POST.get('doctor_id')
            diagnosis.doctor = User.objects.get(pk=doctor_id) if doctor_id else None
            diagnosis.save()

            file_delete_list = json.loads(request.POST.get('files_to_delete', '[]'))
            DiagnosisDocument.objects.filter(id__in=file_delete_list, diagnosis_record=diagnosis).delete()

            for file in request.FILES.getlist('documents'):
                DiagnosisDocument.objects.create(diagnosis_record=diagnosis, file=file)

            return JsonResponse({'message': 'Cập nhật chuẩn đoán thành công'})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@permission_required('diagnosis.delete')
def delete_diagnosis(request, id):
    if request.method == 'POST':
        try:
            diagnosis = DiagnosisRecord.objects.get(id=id)
            diagnosis.delete()
            return JsonResponse({'message': 'Xóa chuẩn đoán thành công'})
        except DiagnosisRecord.DoesNotExist:
            return JsonResponse({'error': 'Không tìm thấy chuẩn đoán'}, status=404)


@permission_required('diagnosis.view')
def get_diagnosis(request, id):
    try:
        diagnosis = DiagnosisRecord.objects.get(id=id)
        documents = diagnosis.documents.all()

        documents_data = [
            {
                'id': doc.id,
                'file_url': doc.file.url,
                'file_name': doc.file.name.split('/')[-1]
            } for doc in documents
        ]

        data = {
            'id': diagnosis.id,
            'patient_id': diagnosis.patient.id,
            'service_type': diagnosis.service_type,
            'department': diagnosis.department,
            'examination_place': diagnosis.examination_place,
            'patient_name': diagnosis.patient.name,
            'examination_time': diagnosis.examination_time.isoformat(),
            'diagnosis_result': diagnosis.diagnosis_result,
            'doctor_id': diagnosis.doctor.id if diagnosis.doctor else '',
            'documents': documents_data
        }

        return JsonResponse(data)
    except DiagnosisRecord.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy chuẩn đoán'}, status=404)


@csrf_exempt
@permission_required('diagnosis.view')
def diagnosis_list_api(request):
    if request.method == 'GET':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        identifier_number = request.GET.get('identifier_number')

        diagnoses = DiagnosisRecord.objects.all()

        if start_date:
            diagnoses = diagnoses.filter(examination_time__date__gte=start_date)
        if end_date:
            diagnoses = diagnoses.filter(examination_time__date__lte=end_date)
        if identifier_number:
            diagnoses = diagnoses.filter(patient__identifier__icontains=identifier_number)

        result = []
        for d in diagnoses:
            result.append({
                'id': d.id,
                'examination_time': d.examination_time.strftime("%Y-%m-%d %H:%M"),
                'patient_code': d.patient.id,
                'service_type': d.service_type,
                'facility_code': d.patient.created_by_facility.name if d.patient.created_by_facility else '',
                'department': d.department,
                'examination_place': d.examination_place,
                'identifier_number': d.patient.identifier,
                'patient_name': d.patient.name,
                'doctor_name': d.doctor.name if d.doctor else '',
            })

        return JsonResponse({'data': result}, safe=False)


@require_GET
def get_doctors_by_patient(request, patient_id):
    try:
        patient = Patient.objects.get(pk=patient_id)
        facility = patient.created_by_facility

        doctors = User.objects.filter(role__code='doctor', facility=facility)
        doctor_list = [
            {'id': d.id, 'name': d.name}
            for d in doctors
        ]

        return JsonResponse({'doctors': doctor_list})
    except Patient.DoesNotExist:
        return JsonResponse({'doctors': []})


def add_month(dt):
    year = dt.year + (dt.month // 12)
    month = dt.month % 12 + 1
    return datetime(year, month, 1)


@permission_required('report.view')
def diagnosis_report(request):
    start_month = request.GET.get('start_month')
    end_month = request.GET.get('end_month')

    if not start_month or not end_month:
        today = datetime.today()
        start_month = end_month = today.strftime('%Y-%m')

    start_date = datetime.strptime(start_month, '%Y-%m').replace(day=1)
    end_dt = datetime.strptime(end_month, '%Y-%m')
    end_date = add_month(end_dt)

    records = DiagnosisRecord.objects.filter(
        examination_time__gte=start_date,
        examination_time__lt=end_date
    )

    facility_stats = records.values(
        'patient__created_by_facility__id',
        'patient__created_by_facility__name'
    ).annotate(
        total_patients=Count('patient', distinct=True),
        total_service_types=Count('service_type', distinct=True)
    ).order_by('patient__created_by_facility__name')

    context = {
        'facility_stats': facility_stats,
        'start_month': start_month,
        'end_month': end_month,
        'tab': 'diagnosis_report'
    }

    return render(request, 'diagnosis_report.html', context)


@csrf_exempt
def generate_public_link(request, id):
    try:
        record = DiagnosisRecord.objects.get(id=id)
        record.generate_public_token()
        public_url = request.build_absolute_uri(f'/diagnosis/public/{record.public_token}/')
        return JsonResponse({'public_url': public_url})
    except DiagnosisRecord.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy bản ghi'}, status=404)


def diagnosis_public_view(request, token):
    try:
        record = DiagnosisRecord.objects.get(public_token=token)
        documents = []

        for d in record.documents.all():
            file_url = d.file.url
            is_image = file_url.lower().endswith(('.jpg', '.jpeg', '.png'))

            documents.append({
                'file_url': file_url,
                'file_name': d.file.name,
                'is_image': is_image
            })

        context = {
            'record': record,
            'documents': documents
        }
        return render(request, 'diagnosis_public.html', context)
    except DiagnosisRecord.DoesNotExist:
        return HttpResponse("Link không hợp lệ hoặc đã bị thu hồi.", status=404)


