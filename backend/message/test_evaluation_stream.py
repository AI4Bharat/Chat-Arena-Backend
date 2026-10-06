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


PAGE = [ANSWER, FINDING,
        dict(ANSWER, id="q2", question="Q2", box=[10, 300, 200, 400], marks_awarded=6, category="minor_mistake"),
        dict(FINDING, id="q2-f1", answer_id="q2", box=[20, 320, 80, 340])]


class ReevaluationTests(TransactionTestCase):
    def setUp(self):
        EvaluationStreamTests.setUp(self)
        self.session = EvaluationStreamTests._session(self)
        self.user_message = Message.objects.create(
            session=self.session, role="user", content="", image_path="ocr-inputs/p1.png", position=0)
        self.page_message = Message.objects.create(
            session=self.session, role="assistant", content=json.dumps(PAGE), model=self.model,
            parent_message_ids=[self.user_message.id], position=1, status="success")

    def _reevaluate(self, **body):
        response = self.client.post(f"/messages/{self.page_message.id}/reevaluate/", body, format="json")
        if response.status_code != 200:
            return response, None
        return response, b"".join(response.streaming_content).decode()

    def _lines(self, body):
        return {line[:3]: json.loads(line[3:]) for line in body.strip().split("\n")}

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_answer_revision_is_merged_saved_and_recorded(self, restream, _signed):
        revised = dict(PAGE[2], marks_awarded=9, category="correct")
        restream.return_value = iter([{"kind": "reply", "text": "Q2 deserves 9."}, revised])

        response, body = self._reevaluate(prompt="Q2 is nearly right", scope="answer", answer_id="q2", batch_id="b1")

        lines = self._lines(body)
        self.assertEqual(lines["ar:"]["text"], "Q2 deserves 9.")
        self.assertEqual(lines["ad:"]["finishReason"], "stop")
        final = lines["af:"]["annotations"]
        self.assertEqual([i["id"] for i in final], ["q1", "q1-f1", "q2"])  # q2's old finding replaced
        revision = lines["af:"]["revision"]
        self.assertEqual((revision["score_before"], revision["score_after"]), ([6, 10], [9, 10]))
        self.assertEqual((revision["question"], revision["batch_id"]), ("Q2", "b1"))
        self.assertNotIn("previous_content", revision)

        self.page_message.refresh_from_db()
        self.assertEqual(json.loads(self.page_message.content), final)
        stored = self.page_message.metadata["eval_revisions"][-1]
        self.assertEqual(stored["previous_content"], PAGE)
        sent = restream.call_args.args[2]
        self.assertEqual((sent.scope, sent.answer_id, sent.feedback), ("answer", "q2", "Q2 is nearly right"))

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_unsaved_edits_are_what_gets_revised(self, restream, _signed):
        edited = [dict(ANSWER, marks_awarded=3)]
        restream.return_value = iter([{"kind": "reply", "text": "ok"}, ANSWER])
        self._reevaluate(prompt="re-check", scope="page", current_annotations=edited)
        self.assertEqual(restream.call_args.args[2].previous, edited)

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_failed_revision_leaves_the_page_untouched(self, restream, _signed):
        def failing(*args, **kwargs):
            yield {"kind": "reply", "text": "half"}
            raise Exception("provider exploded with token abc")
        restream.side_effect = failing
        _, body = self._reevaluate(prompt="re-check", scope="page")
        self.assertNotIn("abc", body)
        self.assertEqual(self._lines(body)["ad:"]["finishReason"], "error")
        self.page_message.refresh_from_db()
        self.assertEqual(json.loads(self.page_message.content), PAGE)
        self.assertNotIn("eval_revisions", self.page_message.metadata)

    def test_request_validation(self):
        self.assertEqual(self._reevaluate(prompt="", scope="page")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x", scope="everything")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x", scope="answer", answer_id="q9")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x" * 2001, scope="page")[0].status_code, 400)
        other = APIClient()
        other.force_authenticate(User.objects.create(email="other@example.com", display_name="Other"))
        response = other.post(f"/messages/{self.page_message.id}/reevaluate/", {"prompt": "x"}, format="json")
        self.assertEqual(response.status_code, 404)

    @mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_only_the_latest_revision_can_be_reverted(self, restream, _signed):
        restream.side_effect = [iter([{"kind": "reply", "text": "one"}, ANSWER]),
                                iter([{"kind": "reply", "text": "two"}])]
        first = self._lines(self._reevaluate(prompt="first", scope="page")[1])["af:"]["revision"]["id"]
        second = self._lines(self._reevaluate(prompt="second", scope="page")[1])["af:"]["revision"]["id"]
        url = f"/messages/{self.page_message.id}/revert_revision/"

        self.assertEqual(self.client.post(url, {"revision_id": first}, format="json").status_code, 400)
        response = self.client.post(url, {"revision_id": second}, format="json")
        self.assertEqual(response.json()["annotations"], [ANSWER])  # back to after the first revision
        response = self.client.post(url, {"revision_id": first}, format="json")
        self.assertEqual(response.json()["annotations"], PAGE)      # and then to the original
        self.page_message.refresh_from_db()
        self.assertEqual(json.loads(self.page_message.content), PAGE)
        self.assertEqual([r["status"] for r in self.page_message.metadata["eval_revisions"]], ["reverted", "reverted"])
