from django.apps import AppConfig


class PrologSurveysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "prolog_surveys"
    label = "prolog_surveys"
    verbose_name = "PROlog surveys"

    def ready(self) -> None:
        from . import conf

        conf.validate()
