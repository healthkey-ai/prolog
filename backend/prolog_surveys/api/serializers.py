from rest_framework import serializers

from ..models import SurveyResponse


class CreateResponseSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    language = serializers.CharField(max_length=12)
    consent = serializers.DictField(required=False)
    invitation = serializers.UUIDField(
        required=False, help_text="Administration id from an invitation link"
    )


class IdentitySerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PatchResponseSerializer(serializers.Serializer):
    last_question_key = serializers.CharField(max_length=128, required=False, allow_blank=True)
    language = serializers.CharField(max_length=12, required=False)


class AnswerSerializer(serializers.Serializer):
    value = serializers.DictField()


class ContactSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


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
        ]
        read_only_fields = fields
