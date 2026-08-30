from django.urls import path

from . import views

urlpatterns = [
    path("surveys/<slug:slug>/", views.SurveyDefinitionView.as_view(), name="run-survey"),
    path("options/<slug:source>/", views.OptionsSourceView.as_view(), name="run-options"),
    path("responses/", views.ResponseCreateView.as_view(), name="run-response-create"),
    path("responses/<uuid:response_id>/", views.ResponseDetailView.as_view(), name="run-response"),
    path(
        "responses/<uuid:response_id>/answers/<slug:question_key>/",
        views.AnswerView.as_view(),
        name="run-answer",
    ),
    path("responses/<uuid:response_id>/submit/", views.SubmitView.as_view(), name="run-submit"),
    path("responses/<uuid:response_id>/contact/", views.ContactView.as_view(), name="run-contact"),
]
