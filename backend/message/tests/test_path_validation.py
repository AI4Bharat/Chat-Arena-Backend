"""
Tests for path traversal prevention in document_utils and serializers.

Verifies that:
- document_utils.extract_text_from_document blocks path traversal.
- MessageCreateSerializer and MessageStreamSerializer path validators
  reject malicious paths and accept valid ones.
"""
from django.test import TestCase
from rest_framework import serializers as drf_serializers
from message.document_utils import extract_text_from_document
from message.serializers import MessageCreateSerializer, MessageStreamSerializer


class DocumentUtilsPathTraversalTests(TestCase):
    """Test extract_text_from_document path validation."""

    def test_blocks_double_dot_traversal(self):
        result = extract_text_from_document("llm-documents-input/../../etc/passwd")
        self.assertIn("Security Error", result)

    def test_blocks_dot_dot_slash(self):
        result = extract_text_from_document("../secret-bucket/file.txt")
        self.assertIn("Security Error", result)

    def test_blocks_wrong_prefix(self):
        result = extract_text_from_document("other-bucket/secret-file.txt")
        self.assertIn("Security Error", result)

    def test_blocks_asr_prefix(self):
        result = extract_text_from_document("asr-audios/user1/audio.wav")
        self.assertIn("Security Error", result)

    def test_returns_none_for_empty_path(self):
        result = extract_text_from_document("")
        self.assertIsNone(result)

    def test_returns_none_for_none_path(self):
        result = extract_text_from_document(None)
        self.assertIsNone(result)


class MessageCreateSerializerPathTests(TestCase):
    """Test path validators on MessageCreateSerializer."""

    def _get_serializer(self):
        return MessageCreateSerializer()

    # ── doc_path ───────────────────────────────────────────────────
    def test_doc_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_doc_path("llm-documents-input/../../etc/passwd")

    def test_doc_path_rejects_wrong_prefix(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_doc_path("asr-audios/user1/file.pdf")

    def test_doc_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_doc_path("llm-documents-input/user1/abc123.pdf")
        self.assertEqual(result, "llm-documents-input/user1/abc123.pdf")

    def test_doc_path_accepts_none(self):
        s = self._get_serializer()
        result = s.validate_doc_path(None)
        self.assertIsNone(result)

    # ── image_path ─────────────────────────────────────────────────
    def test_image_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_image_path("llm-images-input/../../../etc/shadow")

    def test_image_path_rejects_wrong_prefix(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_image_path("llm-documents-input/user1/image.png")

    def test_image_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_image_path("llm-images-input/user1/abc123.png")
        self.assertEqual(result, "llm-images-input/user1/abc123.png")

    # ── audio_path ─────────────────────────────────────────────────
    def test_audio_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_audio_path("asr-audios/../../etc/passwd")

    def test_audio_path_rejects_wrong_prefix(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_audio_path("llm-images-input/user1/audio.wav")

    def test_audio_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_audio_path("asr-audios/user1/abc123.wav")
        self.assertEqual(result, "asr-audios/user1/abc123.wav")


class MessageStreamSerializerPathTests(TestCase):
    """Test path validators on MessageStreamSerializer (defense-in-depth)."""

    def _get_serializer(self):
        return MessageStreamSerializer()

    # ── doc_path ───────────────────────────────────────────────────
    def test_doc_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_doc_path("llm-documents-input/../secret")

    def test_doc_path_rejects_wrong_prefix(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_doc_path("other-bucket/file.pdf")

    def test_doc_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_doc_path("llm-documents-input/user1/doc.pdf")
        self.assertEqual(result, "llm-documents-input/user1/doc.pdf")

    # ── image_path ─────────────────────────────────────────────────
    def test_image_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_image_path("llm-images-input/../../secret")

    def test_image_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_image_path("llm-images-input/user1/img.jpg")
        self.assertEqual(result, "llm-images-input/user1/img.jpg")

    # ── audio_path ─────────────────────────────────────────────────
    def test_audio_path_rejects_traversal(self):
        s = self._get_serializer()
        with self.assertRaises(drf_serializers.ValidationError):
            s.validate_audio_path("asr-audios/../secret")

    def test_audio_path_accepts_valid(self):
        s = self._get_serializer()
        result = s.validate_audio_path("asr-audios/user1/audio.wav")
        self.assertEqual(result, "asr-audios/user1/audio.wav")
