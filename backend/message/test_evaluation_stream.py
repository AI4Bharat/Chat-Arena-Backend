import json
from unittest import mock

from django.test import TransactionTestCase
from rest_framework.test import APIClient

from ai_model.models import AIModel
from chat_session.models import ChatSession
from message.models import Message
from user.models import User

PAGES = [{"path": "ocr-inputs/sheet_p1.png", "width": 1000, "height": 2000},
         {"path": "ocr-inputs/sheet_p2.png", "width": 1000, "height": 2000}]
Q1 = {"id": "q1", "kind": "answer", "question": "Q1", "parts": [{"id": "q1-p1", "page": 1, "box": [10, 10, 200, 100]}],
      "category": "correct", "marks_awarded": 10, "max_marks": 10, "marks_breakdown": [], "comment": "Fully correct."}
# Q3's answer starts on page 1 and continues on page 2: one answer, two boxes.
Q3 = dict(Q1, id="q3", question="Q3", marks_awarded=6, category="minor_mistake",
          parts=[{"id": "q3-p1", "page": 1, "box": [10, 1800, 900, 1990]},
                 {"id": "q3-p2", "page": 2, "box": [10, 20, 900, 200]}])
Q3_FINDING = {"id": "q3-f1", "kind": "finding", "answer_id": "q3", "page": 2, "box": [20, 50, 400, 90],
              "category": "minor_mistake", "comment": "200 - 135 is 65.", "marks_impact": -1}
SHEET = [Q1, Q3, Q3_FINDING]
signed = mock.patch("message.views.generate_signed_url", side_effect=lambda path, exp=900: f"https://signed/{path}")


def lines(body):
    return [(line[:3], json.loads(line[3:])) for line in body.strip().split("\n")]


class EvaluationTestCase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(email="teacher@example.com", display_name="Teacher")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.model = AIModel.objects.create(
            provider="google", model_name="gemini-2.5-pro", model_code="google-eval/gemini-2.5-pro",
            model_type="EVAL", display_name="Gemini 2.5 Pro",
        )
        self.session = ChatSession.objects.create(
            user=self.user, mode="direct", session_type="EVAL", model_a=self.model,
            metadata={"max_marks": 10, "instructions": "Be strict", "answer_pages": PAGES,
                      "reference_pages": [{"path": "ocr-inputs/key_p1.png"}, {"path": "../secrets/x.png"}],
                      "source_filename": "class7_unit_test.pdf"},
        )


class EvaluateDocumentTests(EvaluationTestCase):
    def _evaluate(self, session=None):
        response = self.client.post("/messages/evaluate_document/", {"session_id": str((session or self.session).id)},
                                    format="json")
        body = b"".join(response.streaming_content).decode() if response.status_code == 200 else None
        return response, body

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_evaluation")
    def test_whole_sheet_is_evaluated_in_one_call_and_saved(self, stream_evaluation, _signed):
        stream_evaluation.return_value = iter(SHEET)

        response, body = self._evaluate()

        out = lines(body)
        self.assertEqual([tag for tag, _ in out], ["am:", "aa:", "aa:", "aa:", "ad:"])
        self.assertEqual(out[2][1]["parts"][1]["page"], 2)
        pages = stream_evaluation.call_args.args[0]
        self.assertEqual([(p.number, p.url, p.width) for p in pages],
                         [(1, "https://signed/ocr-inputs/sheet_p1.png", 1000), (2, "https://signed/ocr-inputs/sheet_p2.png", 1000)])
        kwargs = stream_evaluation.call_args.kwargs
        self.assertEqual(kwargs["reference_urls"], ["https://signed/ocr-inputs/key_p1.png"])
        self.assertEqual((kwargs["instructions"], kwargs["max_marks"]), ("Be strict", 10))

        page_messages = list(self.session.messages.filter(role="user").order_by("created_at"))
        self.assertEqual([m.image_path for m in page_messages], [p["path"] for p in PAGES])
        evaluation = self.session.messages.get(role="assistant")
        self.assertEqual(str(evaluation.id), out[0][1]["message_id"])
        self.assertEqual(evaluation.parent_message_ids, [m.id for m in page_messages])
        self.assertEqual((evaluation.status, json.loads(evaluation.content)), ("success", SHEET))

        self.assertEqual(self._evaluate()[0].status_code, 409)  # re-evaluation goes through reevaluate

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_evaluation")
    def test_failed_run_keeps_partial_results_and_can_be_retried(self, stream_evaluation, _signed):
        def failing(*args, **kwargs):
            yield Q1
            raise Exception("upstream said: key=secret-value")
        stream_evaluation.side_effect = failing

        _, body = self._evaluate()
        self.assertNotIn("secret-value", body)
        self.assertEqual(lines(body)[-1][1]["error"], "Evaluation failed. Please try again.")
        evaluation = self.session.messages.get(role="assistant")
        self.assertEqual((evaluation.status, json.loads(evaluation.content)), ("error", [Q1]))

        stream_evaluation.side_effect = None
        stream_evaluation.return_value = iter(SHEET)
        self._evaluate()
        self.assertEqual(self.session.messages.filter(role="user").count(), 2)  # pages not duplicated
        self.assertEqual(json.loads(self.session.messages.get(role="assistant").content), SHEET)

    def test_request_validation(self):
        bad = ChatSession.objects.create(user=self.user, mode="direct", session_type="EVAL", model_a=self.model,
                                         metadata={"answer_pages": [{"path": "tts-audios/x.wav"}]})
        self.assertEqual(self._evaluate(bad)[0].status_code, 400)
        ocr = ChatSession.objects.create(user=self.user, mode="direct", session_type="OCR", model_a=self.model)
        self.assertEqual(self._evaluate(ocr)[0].status_code, 400)
        too_long = ChatSession.objects.create(user=self.user, mode="direct", session_type="EVAL", model_a=self.model,
                                              metadata={"answer_pages": [PAGES[0]] * 21})
        self.assertEqual(self._evaluate(too_long)[0].status_code, 400)
        for missing in ({}, {"session_id": ""}, {"session_id": "not-a-uuid"}):
            self.assertEqual(self.client.post("/messages/evaluate_document/", missing, format="json").status_code, 400)
        other = APIClient()
        other.force_authenticate(User.objects.create(email="other@example.com", display_name="Other"))
        response = other.post("/messages/evaluate_document/", {"session_id": str(self.session.id)}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_generate_title_uses_source_filename(self):
        response = self.client.post(f"/sessions/{self.session.id}/generate_title/")
        self.assertEqual(response.json()["title"], "Evaluation: class7 unit test")


class ReevaluationTests(EvaluationTestCase):
    def setUp(self):
        super().setUp()
        self.page_messages = [Message.objects.create(session=self.session, role="user", content="",
                                                     image_path=p["path"], position=i) for i, p in enumerate(PAGES)]
        self.evaluation = Message.objects.create(
            session=self.session, role="assistant", content=json.dumps(SHEET), model=self.model,
            parent_message_ids=[m.id for m in self.page_messages], position=2, status="success")

    def _reevaluate(self, **body):
        response = self.client.post(f"/messages/{self.evaluation.id}/reevaluate/", body, format="json")
        if response.status_code != 200:
            return response, None
        return response, dict(lines(b"".join(response.streaming_content).decode()))

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_answer_across_pages_is_revised_as_one(self, restream, _signed):
        revised = dict(Q3, marks_awarded=8, category="correct")
        restream.return_value = iter([{"kind": "reply", "text": "Q3 deserves 8."}, revised])

        _, out = self._reevaluate(prompt="Q3 is nearly right", scope="answer", answer_id="q3")

        self.assertEqual(out["ar:"]["text"], "Q3 deserves 8.")
        final = out["af:"]["annotations"]
        self.assertEqual([i["id"] for i in final], ["q1", "q3"])  # q3's old finding replaced
        self.assertEqual([p["page"] for p in final[1]["parts"]], [1, 2])
        revision = out["af:"]["revision"]
        self.assertEqual((revision["score_before"], revision["score_after"]), ([6, 10], [8, 10]))
        self.assertEqual(revision["question"], "Q3")
        self.assertNotIn("previous_content", revision)

        pages, _, sent = restream.call_args.args
        self.assertEqual([p.number for p in pages], [1, 2])
        self.assertEqual((sent.scope, sent.answer_id, sent.target_ids), ("answer", "q3", {"q3"}))
        self.evaluation.refresh_from_db()
        self.assertEqual(json.loads(self.evaluation.content), final)
        self.assertEqual(self.evaluation.metadata["eval_revisions"][-1]["previous_content"], SHEET)

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_page_scope_targets_answers_with_a_box_on_that_page(self, restream, _signed):
        restream.return_value = iter([{"kind": "reply", "text": "ok"}, dict(Q3, marks_awarded=5)])
        edited = [dict(Q1, marks_awarded=3), Q3, Q3_FINDING]  # unsaved edit to Q1

        _, out = self._reevaluate(prompt="re-check page 2", scope="page", page=2, current_annotations=edited)

        sent = restream.call_args.args[2]
        self.assertEqual((sent.page, sent.target_ids, sent.previous), (2, {"q3"}, edited))
        self.assertEqual([(i["id"], i.get("marks_awarded")) for i in out["af:"]["annotations"]],
                         [("q1", 3), ("q3", 5)])

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_failed_revision_leaves_the_sheet_untouched(self, restream, _signed):
        def failing(*args, **kwargs):
            yield {"kind": "reply", "text": "half"}
            raise Exception("provider exploded with token abc")
        restream.side_effect = failing
        _, out = self._reevaluate(prompt="re-check", scope="document")
        self.assertEqual(out["ad:"]["finishReason"], "error")
        self.assertNotIn("abc", json.dumps(out))
        self.evaluation.refresh_from_db()
        self.assertEqual(json.loads(self.evaluation.content), SHEET)
        self.assertNotIn("eval_revisions", self.evaluation.metadata)

    def test_request_validation(self):
        self.assertEqual(self._reevaluate(prompt="", scope="document")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x", scope="everything")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x", scope="answer", answer_id="q9")[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x", scope="page", page=3)[0].status_code, 400)
        self.assertEqual(self._reevaluate(prompt="x" * 2001, scope="document")[0].status_code, 400)
        other = APIClient()
        other.force_authenticate(User.objects.create(email="other@example.com", display_name="Other"))
        response = other.post(f"/messages/{self.evaluation.id}/reevaluate/", {"prompt": "x"}, format="json")
        self.assertEqual(response.status_code, 404)

    @signed
    @mock.patch("ai_model.evaluation_interactions.stream_reevaluation")
    def test_only_the_latest_revision_can_be_reverted(self, restream, _signed):
        restream.side_effect = [iter([{"kind": "reply", "text": "one"}, dict(Q1, marks_awarded=1)]),
                                iter([{"kind": "reply", "text": "two"}, dict(Q1, marks_awarded=2)])]
        first = self._reevaluate(prompt="first", scope="document")[1]["af:"]["revision"]["id"]
        second = self._reevaluate(prompt="second", scope="document")[1]["af:"]["revision"]["id"]
        url = f"/messages/{self.evaluation.id}/revert_revision/"

        self.assertEqual(self.client.post(url, {"revision_id": first}, format="json").status_code, 400)
        after_first = self.client.post(url, {"revision_id": second}, format="json").json()["annotations"]
        self.assertEqual(after_first, [dict(Q1, marks_awarded=1), Q3, Q3_FINDING])
        self.assertEqual(self.client.post(url, {"revision_id": first}, format="json").json()["annotations"], SHEET)
        self.evaluation.refresh_from_db()
        self.assertEqual(json.loads(self.evaluation.content), SHEET)
        self.assertEqual([r["status"] for r in self.evaluation.metadata["eval_revisions"]], ["reverted", "reverted"])
