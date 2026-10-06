import json
import uuid
from unittest import mock

from django.test import TransactionTestCase
from rest_framework.test import APIClient

from ai_model.models import AIModel
from chat_session.models import ChatSession
from message.models import Message
from user.models import User

ANSWER = {"id": "q1", "kind": "answer", "question": "Q1", "box": [10, 10, 200, 100],
          "category": "correct", "marks_awarded": 10, "max_marks": 10,
          "marks_breakdown": [], "comment": "Fully correct.", "page": 1}
FINDING = {"id": "q1-f1", "kind": "finding", "answer_id": "q1", "box": [20, 20, 80, 40],
           "category": "correct", "comment": "Good working.", "marks_impact": 0, "page": 1}


class EvaluationStreamTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(email="teacher@example.com", display_name="Teacher")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.model = AIModel.objects.create(
            provider="google", model_name="gemini-2.5-pro", model_code="google-eval/gemini-2.5-pro",
            model_type="EVAL", display_name="Gemini 2.5 Pro",
        )

    def _session(self, **metadata):
        return ChatSession.objects.create(
            user=self.user, mode="direct", session_type="EVAL", model_a=self.model,
            metadata={"max_marks": 10, "instructions": "Be strict", **metadata},
        )

    def _stream(self, session, image_path="ocr-inputs/abc_p1.png"):
        user_id, assistant_id = str(uuid.uuid4()), str(uuid.uuid4())
        response = self.client.post("/messages/stream/", {
            "session_id": str(session.id),
            "mode": "OCR",
            "messages": [
                {"id": user_id, "role": "user", "image_path": image_path, "content": "", "status": "pending"},
                {"id": assistant_id, "role": "assistant", "content": "", "parent_message_ids": [user_id],
                 "status": "pending", "participant": "a"},
            ],
        }, format="json")
        body = b"".join(response.streaming_content).decode()
        return response, body, assistant_id

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_evaluation")
    def test_streams_annotations_and_persists_them(self, stream_evaluation, _signed):
        stream_evaluation.return_value = iter([ANSWER, FINDING])
        session = self._session(reference_pages=[{"path": "ocr-inputs/key_p1.png"},
                                                 {"path": "../secrets/other.png"}])

        response, body, assistant_id = self._stream(session)

        self.assertEqual(response.status_code, 200)
        lines = body.strip().split("\n")
        self.assertEqual([line[:3] for line in lines], ["aa:", "aa:", "ad:"])
        self.assertEqual(json.loads(lines[1][3:])["answer_id"], "q1")
        self.assertEqual(json.loads(lines[2][3:])["finishReason"], "stop")

        args, kwargs = stream_evaluation.call_args
        self.assertEqual(args, ("https://signed/ocr-inputs/abc_p1.png", "google-eval/gemini-2.5-pro"))
        self.assertEqual(kwargs["reference_urls"], ["https://signed/ocr-inputs/key_p1.png"])
        self.assertEqual(kwargs["instructions"], "Be strict")
        self.assertEqual(kwargs["max_marks"], 10)

        saved = Message.objects.get(id=assistant_id)
        self.assertEqual(saved.status, "success")
        self.assertEqual(json.loads(saved.content), [ANSWER, FINDING])

    @mock.patch("ai_model.evaluation_interactions.stream_evaluation")
    def test_rejects_image_outside_upload_prefix(self, stream_evaluation):
        response, body, assistant_id = self._stream(self._session(), image_path="tts-audios/x.wav")

        finish = json.loads(body.strip()[3:])
        self.assertEqual(finish["finishReason"], "error")
        self.assertEqual(finish["error"], "Answer sheet image is missing or invalid.")
        stream_evaluation.assert_not_called()
        self.assertEqual(Message.objects.get(id=assistant_id).status, "error")

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_evaluation")
    def test_provider_errors_are_not_shown_to_the_user(self, stream_evaluation, _signed):
        def failing(*args, **kwargs):
            yield ANSWER
            raise Exception("upstream said: key=secret-value")
        stream_evaluation.side_effect = failing

        response, body, assistant_id = self._stream(self._session())

        lines = body.strip().split("\n")
        self.assertEqual([line[:3] for line in lines], ["aa:", "ad:"])
        self.assertNotIn("secret-value", body)
        self.assertEqual(json.loads(lines[1][3:])["error"], "Evaluation failed. Please try again.")
        saved = Message.objects.get(id=assistant_id)
        self.assertEqual((saved.status, json.loads(saved.content)), ("error", [ANSWER]))  # partial result kept

    def test_generate_title_uses_source_filename(self):
        session = self._session(source_filename="class7_unit_test.pdf")
        response = self.client.post(f"/sessions/{session.id}/generate_title/")
        self.assertEqual(response.json()["title"], "Evaluation: class7 unit test")
