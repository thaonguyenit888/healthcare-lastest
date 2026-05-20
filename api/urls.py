from django.urls import path
from .views import *

urlpatterns = [
    path('', lambda request: redirect('patient_login'), name='root_redirect'),
    path('facilities/', facility_list, name='facility_list'),
    path('services/', service_list, name='service_list'),
    path('reports/', report_list, name='report_list'),
    path('users/', user_list, name='user_list'),
    path('roles/', role_list, name='role_list'),
    path('permissions/', permission_list, name='permission_list'),
    path('patients/', patient_list, name='patient_list'),
    path('examinations/', examination_list, name='examination_list'),
    path('examinations/<int:pk>/', examination_detail, name='examination_detail'),
    path('dashboard/', dashboard, name='dashboard'),
    path('diagnosis/', diagnosis_list, name='diagnosis_list'),

    # Patient portal
    path('lookup/login/', patient_login_view, name='patient_login'),
    path('lookup/logout/', patient_logout_view, name='patient_logout'),
    path('lookup/', patient_dashboard, name='patient_dashboard'),
    path('lookup/my-results/', patient_my_results, name='patient_my_results'),
    path('lookup/my-results/<int:pk>/', patient_my_result_detail, name='patient_my_result_detail'),
    path('lookup/results/<int:pk>/', patient_lookup_result_detail, name='patient_lookup_result_detail'),
    path('api/patient-lookup/', patient_lookup_api, name='patient_lookup_api'),
    path('api/patient-lookup/patients/', patient_lookup_patients_api, name='patient_lookup_patients_api'),
    path('api/patient-lookup/exams/', patient_lookup_exams_api, name='patient_lookup_exams_api'),

    path('api/facilities/<int:pk>/', get_facility, name='get_facility'),
    path('api/facilities/create/', create_facility, name='create_facility'),
    path('api/facilities/update/<int:pk>/', update_facility, name='update_facility'),
    path('api/facilities/delete/<int:pk>/', delete_facility, name='delete_facility'),
    path('api/facilities/<int:pk>/services/', update_facility_services, name='update_facility_services'),

    path('api/services/create/', create_service, name='create_service'),
    path('api/services/update/<int:pk>/', update_service, name='update_service'),
    path('api/services/delete/<int:pk>/', delete_service, name='delete_service'),

    path('api/users/create/', create_user),
    path('api/users/update/<int:pk>/', update_user),
    path('api/users/delete/<int:pk>/', delete_user),

    path('api/roles/<int:pk>/', get_role, name='get_role'),
    path('api/roles/create/', create_role, name='create_role'),
    path('api/roles/update/<int:pk>/', update_role, name='update_role'),
    path('api/roles/delete/<int:pk>/', delete_role, name='delete_role'),

    path('api/permissions/create/', create_permission, name='create_permission'),
    path('api/permissions/update/<int:pk>/', update_permission, name='update_permission'),
    path('api/permissions/delete/<int:pk>/', delete_permission, name='delete_permission'),

    path('api/patients/<int:pk>/', get_patient),
    path('api/patients/create/', create_patient),
    path('api/patients/update/<int:pk>/', update_patient),
    path('api/patients/delete/<int:pk>/', delete_patient),

    path('api/examinations/<int:pk>/', get_examination, name='get_examination'),
    path('api/examinations/create/', create_examination, name='create_examination'),
    path('api/examinations/update/<int:pk>/', update_examination, name='update_examination'),
    path('api/examinations/delete/<int:pk>/', delete_examination, name='delete_examination'),
    path('api/facilities/<int:pk>/services-list/', get_facility_services_api, name='get_facility_services_api'),
    path('api/examination-services/update/<int:pk>/', update_examination_service, name='update_examination_service'),
    path('api/examinations/<int:pk>/overall/', update_examination_overall, name='update_examination_overall'),
    path('api/examinations/<int:pk>/status/', update_examination_status, name='update_examination_status'),
    path('api/examinations/doc/delete/<int:pk>/', delete_examination_doc, name='delete_examination_doc'),
    path('api/examinations/consults/update/<int:pk>/', update_examination_consult, name='update_examination_consult'),

    path('api/diagnosis/create/', create_diagnosis, name='create_diagnosis'),
    path('api/diagnosis/update/<int:id>/', update_diagnosis, name='update_diagnosis'),
    path('api/diagnosis/delete/<int:id>/', delete_diagnosis, name='delete_diagnosis'),
    path('api/diagnosis/<int:id>/', get_diagnosis, name='get_diagnosis'),
    path('api/diagnosis/list/', diagnosis_list_api, name='diagnosis_list_api'),

    path('api/get_doctors_by_patient/<int:patient_id>/', get_doctors_by_patient, name='get_doctors_by_patient'),
    path('diagnosis_report/', diagnosis_report, name='diagnosis_report'),

    path('api/diagnosis/generate_public_link/<int:id>/', generate_public_link, name='generate_public_link'),
    path('diagnosis/public/<str:token>/', diagnosis_public_view, name='diagnosis_public_view'),
]
