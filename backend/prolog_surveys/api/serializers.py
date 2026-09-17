from rest_framework import serializers

from ..models import SurveyResponse


class CreateResponseSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    language = serializers.CharField(max_length=12)
    consent = serializers.DictField(required=False)
    invitation = serializers.UUIDField(
        required=False, help_text="Administration id from an invitation link"
    )


class PatchResponseSerializer(serializers.Serializer):
    last_question_key = serializers.CharField(max_length=128, required=False, allow_blank=True)
    language = serializers.CharField(max_length=12, required=False)


class AnswerSerializer(serializers.Serializer):
    value = serializers.DictField()


class ContactSerializer(serializers.Serializer):
    """An email address, and the consents ticked with it, for the contact and
    identity endpoints (CON-3/4). Keys are checked against the question's
    ``config.consents`` in the view."""

    email = serializers.EmailField(max_length=254)
    consents = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list, max_length=5
    )
    # Contact capture only: the receipt from the earlier capture this one replaces.
    receipt = serializers.CharField(required=False, allow_blank=True, max_length=43)


class ReceiptSerializer(serializers.Serializer):
    """The receipt alone: what removing a captured address takes."""

    receipt = serializers.CharField(max_length=43)


class ResponseSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="survey_version.survey.slug", read_only=True)
    version = serializers.CharField(source="survey_version.version", read_only=True)

    class Meta:
        model = SurveyResponse
        fields = [
            "id",
            "slug",
            "version",
            "language",
            "status",
            "started_at",
            "submitted_at",
            "last_question_key",
            "administration",
        ]
        read_only_fields = fields
