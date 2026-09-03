from django.urls import path

from . import themes, views

urlpatterns = [
    path("surveys/<slug:slug>/", views.SurveyDefinitionView.as_view(), name="run-survey"),
    path("options/<slug:source>/", views.OptionsSourceView.as_view(), name="run-options"),
    path("legal/<slug:page>/", views.LegalPageView.as_view(), name="run-legal"),
    path("themes/<slug:code>/", themes.ThemeView.as_view(), name="run-theme"),
    path(
        "themes/<slug:code>/assets/<path:path>",
        themes.ThemeAssetView.as_view(),
        name="run-theme-asset",
    ),
    path("responses/", views.ResponseCreateView.as_view(), name="run-response-create"),
    path("responses/<uuid:response_id>/", views.ResponseDetailView.as_view(), name="run-response"),
    path(
        "responses/<uuid:response_id>/answers/<slug:question_key>/",
        views.AnswerView.as_view(),
        name="run-answer",
    ),
    path("responses/<uuid:response_id>/submit/", views.SubmitView.as_view(), name="run-submit"),
    path("responses/<uuid:response_id>/contact/", views.ContactView.as_view(), name="run-contact"),
    path(
        "responses/<uuid:response_id>/identity/", views.IdentityView.as_view(), name="run-identity"
    ),
]
