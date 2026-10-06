import json

from django.test import SimpleTestCase

from ai_model.evaluation_interactions import (
    EvaluationNormalizer,
    build_evaluation_prompt,
    build_user_content,
    clamp_max_marks,
    iter_json_objects,
    normalize_category,
)


def png_bytes(width, height):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


def chunked(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


ANSWER = {
    "kind": "answer", "id": "q1", "question": "Q1", "question_text": "Find 7 x 8 + 12",
    "box_2d": [100, 50, 300, 950], "category": "Minor Mistake", "marks_awarded": 7.3,
    "max_marks": 10,
    "marks_breakdown": [{"criterion": "Method", "awarded": 5, "max": 5},
                        {"criterion": "Accuracy", "awarded": 2, "max": 5}],
    "comment": "Correct method; arithmetic slip {in} step 2.",
}
FINDING = {
    "kind": "finding", "id": "q1-f1", "answer_id": "q1", "box_2d": [150, 60, 180, 400],
    "category": "major", "comment": "7 x 8 is 56, not 54.", "marks_impact": -2,
}


class IterJsonObjectsTests(SimpleTestCase):
    def test_objects_split_across_arbitrary_chunks(self):
        text = "```json\n[" + json.dumps(ANSWER) + ",\n" + json.dumps(FINDING) + "]\n```"
        for size in (1, 3, 17, len(text)):
            objects = list(iter_json_objects(chunked(text, size)))
            self.assertEqual([o["id"] for o in objects], ["q1", "q1-f1"], size)
            self.assertEqual(objects[0]["marks_breakdown"][1]["criterion"], "Accuracy")

    def test_braces_and_escaped_quotes_inside_strings(self):
        item = dict(FINDING, comment='Wrote "}{" and \\"x\\" instead of y')
        objects = list(iter_json_objects(chunked(json.dumps([item]), 2)))
        self.assertEqual(objects[0]["comment"], item["comment"])

    def test_wrapper_object_is_unwrapped(self):
        text = json.dumps({"annotations": [ANSWER, FINDING]})
        self.assertEqual(len(list(iter_json_objects([text]))), 2)

    def test_invalid_object_is_skipped(self):
        text = '[{"kind": "answer", "id": oops}, ' + json.dumps(FINDING) + "]"
        self.assertEqual([o["id"] for o in iter_json_objects([text])], ["q1-f1"])


class NormalizerTests(SimpleTestCase):
    def setUp(self):
        self.norm = EvaluationNormalizer(img_width=1000, img_height=2000, max_marks=10)

    def test_answer_box_marks_and_category(self):
        answer = self.norm.add(ANSWER)
        self.assertEqual(answer["kind"], "answer")
        self.assertEqual(answer["box"], [50, 200, 950, 600])  # [ymin,xmin,ymax,xmax]/1000 -> px
        self.assertEqual(answer["category"], "minor_mistake")
        self.assertEqual(answer["marks_awarded"], 7.5)  # rounded to 0.5
        self.assertEqual(answer["max_marks"], 10)
        self.assertEqual(len(answer["marks_breakdown"]), 2)

    def test_finding_links_to_answer_and_impact_is_negative(self):
        self.norm.add(ANSWER)
        finding = self.norm.add(dict(FINDING, marks_impact=2))
        self.assertEqual(finding["answer_id"], "q1")
        self.assertEqual(finding["category"], "major_mistake")
        self.assertEqual(finding["marks_impact"], -2)

    def test_duplicate_ids_are_made_unique_and_findings_follow_the_renamed_answer(self):
        self.norm.add(ANSWER)
        second = self.norm.add(dict(ANSWER, question="Q2"))
        finding = self.norm.add(dict(FINDING, answer_id="unknown"))
        self.assertEqual(second["id"], "q1-2")
        self.assertEqual(finding["answer_id"], "q1-2")  # falls back to the latest answer

    def test_marks_are_clamped_and_missing_marks_come_from_breakdown(self):
        over = self.norm.add(dict(ANSWER, marks_awarded=14))
        self.assertEqual(over["marks_awarded"], 10)
        derived = self.norm.add({k: v for k, v in ANSWER.items() if k != "marks_awarded"})
        self.assertEqual(derived["marks_awarded"], 7)

    def test_bad_box_becomes_none(self):
        self.assertIsNone(self.norm.add(dict(ANSWER, box_2d=[1, 2, 3]))["box"])
        self.assertIsNone(self.norm.add(dict(ANSWER, box_2d=[500, 500, 500, 500]))["box"])
        swapped = self.norm.add(dict(ANSWER, box_2d=[300, 950, 100, 50]))
        self.assertEqual(swapped["box"], [50, 200, 950, 600])

    def test_finding_without_any_answer_has_no_parent(self):
        self.assertIsNone(self.norm.add(FINDING)["answer_id"])


class PromptTests(SimpleTestCase):
    def test_categories(self):
        self.assertEqual(normalize_category("Major-Mistake"), "major_mistake")
        self.assertEqual(normalize_category("not attempted"), "unattempted")
        self.assertEqual(normalize_category("???"), "minor_mistake")

    def test_max_marks_clamp_and_prompt(self):
        self.assertEqual(clamp_max_marks("abc"), 10)
        self.assertEqual(clamp_max_marks(-3), 10)
        self.assertEqual(clamp_max_marks(500), 100)
        self.assertIn("out of 5 marks", build_evaluation_prompt(5))

    def test_student_page_is_last_and_instructions_are_delimited(self):
        content = build_user_content("data:student", ["data:ref1", "data:ref2"], "Be strict")
        images = [c["image_url"]["url"] for c in content if c["type"] == "image_url"]
        self.assertEqual(images, ["data:ref1", "data:ref2", "data:student"])
        self.assertTrue(any("<<<\nBe strict\n>>>" in c.get("text", "") for c in content))


class GeminiStreamTests(SimpleTestCase):
    """The OpenAI-compatible streaming call, with the network replaced by fakes."""

    def test_streamed_tokens_become_normalized_annotations(self):
        from types import SimpleNamespace
        from unittest import mock
        from ai_model import evaluation_interactions as ev

        text = "```json\n[" + json.dumps(ANSWER) + "," + json.dumps(FINDING) + "]\n```"
        chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
                  for piece in chunked(text, 7)] + [SimpleNamespace(choices=[])]
        create = mock.Mock(return_value=iter(chunks))
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        response = mock.Mock(content=png_bytes(400, 800), headers={"Content-Type": "image/png"})
        response.raise_for_status = mock.Mock()

        with mock.patch.object(ev, "OpenAI", return_value=fake_client), \
                mock.patch.object(ev.requests, "get", return_value=response), \
                mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            items = list(ev.stream_evaluation("https://img/student.png", "google-eval/gemini-2.5-pro",
                                              reference_urls=["https://img/key.png"], instructions="Be fair",
                                              max_marks=10))

        self.assertEqual([i["kind"] for i in items], ["answer", "finding"])
        self.assertEqual(items[0]["box"], [20, 80, 380, 240])  # 400x800 page
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-2.5-pro")
        self.assertTrue(kwargs["stream"])
        images = [c for c in kwargs["messages"][1]["content"] if c["type"] == "image_url"]
        self.assertEqual(len(images), 2)  # reference page + student page

    def test_missing_api_key_is_reported_clearly(self):
        from unittest import mock
        from ai_model import evaluation_interactions as ev
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(ev.EvaluationError, "GOOGLE_API_KEY is not configured"):
                list(ev.stream_evaluation("https://img/x.png", "google-eval/gemini-2.5-pro"))

    def test_unknown_provider_is_rejected(self):
        from ai_model import evaluation_interactions as ev
        with self.assertRaises(ev.EvaluationError):
            ev.stream_evaluation("https://img/x.png", "openai/gpt-4o")


class RevisionTests(SimpleTestCase):
    def setUp(self):
        from ai_model import evaluation_interactions as ev
        self.ev = ev
        norm = EvaluationNormalizer(img_width=1000, img_height=2000, max_marks=10)
        self.page = [norm.add(ANSWER), norm.add(FINDING),
                     norm.add(dict(ANSWER, id="q2", question="Q2", box_2d=[400, 50, 600, 950])),
                     norm.add(dict(FINDING, id="q2-f1", answer_id="q2", box_2d=[450, 60, 480, 400]))]

    def test_model_format_round_trips_boxes(self):
        raw = self.ev.to_model_format(self.page, 1000, 2000)
        self.assertNotIn("box", raw[0])
        again = EvaluationNormalizer(1000, 2000).add(raw[0])
        self.assertEqual(again["box"], self.page[0]["box"])

    def test_answer_merge_replaces_only_that_answer_and_its_findings(self):
        revised_answer = dict(self.page[2], id="q2-x", box=None, marks_awarded=9, category="minor_mistake")
        revised_finding = dict(self.page[3], id="q2-f9", answer_id="q2-x", comment="unit should be cm")
        merged = self.ev.merge_revision(self.page, [revised_answer, revised_finding], "answer", "q2")
        self.assertEqual([i["id"] for i in merged], ["q1", "q1-f1", "q2", "q2-f9"])
        self.assertEqual(merged[2]["marks_awarded"], 9)
        self.assertEqual(merged[2]["box"], self.page[2]["box"])  # model gave no box: keep the old one
        self.assertEqual(merged[3]["answer_id"], "q2")
        self.assertIs(merged[0], self.page[0])

    def test_answer_merge_without_a_revised_answer_is_an_error(self):
        with self.assertRaises(self.ev.EvaluationError):
            self.ev.merge_revision(self.page, [self.page[3]], "answer", "q2")

    def test_page_merge_is_a_replacement(self):
        self.assertEqual(self.ev.merge_revision(self.page, self.page[:2], "page"), self.page[:2])

    def test_revise_objects_keeps_one_reply_and_unique_ids(self):
        revision = self.ev.Revision(feedback="x", scope="answer", answer_id="q2", previous=self.page)
        raw = [{"kind": "reply", "text": "Changed Q2."}, {"kind": "reply", "text": "again"},
               dict(ANSWER, id="q2"), dict(FINDING, id="q1-f1", answer_id="q2")]
        out = list(self.ev.revise_objects(iter(raw), 1000, 2000, 10, revision))
        self.assertEqual(out[0], {"kind": "reply", "text": "Changed Q2."})
        self.assertEqual([o.get("id") for o in out[1:]], ["q2", "q1-f1-2"])  # q1-f1 belongs to Q1

    def test_scope_score(self):
        self.assertEqual(self.ev.scope_score(self.page, "page"), (15, 20))
        self.assertEqual(self.ev.scope_score(self.page, "answer", "q2"), (7.5, 10))

    def test_gemini_revision_prompt_carries_previous_evaluation_and_feedback(self):
        from types import SimpleNamespace
        from unittest import mock
        text = json.dumps([{"kind": "reply", "text": "Deducted a mark for units."}, dict(ANSWER, id="q2")])
        chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))]) for p in chunked(text, 9)]
        create = mock.Mock(return_value=iter(chunks))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        response = mock.Mock(content=png_bytes(1000, 2000), headers={"Content-Type": "image/png"})
        revision = self.ev.Revision(feedback="Q2 perimeter unit is cm", scope="answer", answer_id="q2",
                                    previous=self.page, history=[{"feedback": "be strict", "reply": "ok"}])
        with mock.patch.object(self.ev, "OpenAI", return_value=client), \
                mock.patch.object(self.ev.requests, "get", return_value=response), \
                mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "k"}):
            out = list(self.ev.stream_reevaluation("https://img/p.png", "google-eval/gemini-2.5-pro", revision))

        self.assertEqual(out[0]["text"], "Deducted a mark for units.")
        self.assertEqual(out[1]["kind"], "answer")
        messages = create.call_args.kwargs["messages"]
        self.assertIn("REVISING", messages[0]["content"])
        self.assertIn('ONLY the revised answer with id "q2"', messages[0]["content"])
        texts = "\n".join(c.get("text", "") for c in messages[1]["content"])
        self.assertIn('"box_2d": [400, 50, 600, 950]', texts)
        self.assertIn("Q2 perimeter unit is cm", texts)
        self.assertIn("Teacher: be strict", texts)

    def test_answer_scope_needs_an_existing_answer(self):
        revision = self.ev.Revision(feedback="x", scope="answer", answer_id="nope", previous=self.page)
        with self.assertRaises(self.ev.EvaluationError):
            self.ev.stream_reevaluation("https://img/p.png", "google-eval/gemini-2.5-pro", revision)
