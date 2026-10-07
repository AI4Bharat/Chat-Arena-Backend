import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from ai_model import evaluation_interactions as ev
from ai_model.evaluation_interactions import (
    EvaluationNormalizer,
    Revision,
    SheetPage,
    build_evaluation_prompt,
    build_user_content,
    clamp_max_marks,
    iter_json_objects,
    normalize_category,
)

SIZES = {1: (1000, 2000), 2: (1000, 2000)}


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
    "parts": [{"page": 1, "box_2d": [100, 50, 300, 950]}], "category": "Minor Mistake", "marks_awarded": 7.3,
    "max_marks": 10,
    "marks_breakdown": [{"criterion": "Method", "awarded": 5, "max": 5},
                        {"criterion": "Accuracy", "awarded": 2, "max": 5}],
    "comment": "Correct method; arithmetic slip {in} step 2.",
}
FINDING = {
    "kind": "finding", "id": "q1-f1", "answer_id": "q1", "page": 1, "box_2d": [150, 60, 180, 400],
    "category": "major", "comment": "7 x 8 is 56, not 54.", "marks_impact": -2,
}
# Q3 starts at the foot of page 1 and continues at the top of page 2.
SPANNING = dict(ANSWER, id="q3", question="Q3",
                parts=[{"page": 1, "box_2d": [900, 50, 980, 950]}, {"page": 2, "box_2d": [20, 50, 120, 950]}])


def gemini_client(text, piece=7):
    chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))]) for p in chunked(text, piece)]
    create = mock.Mock(return_value=iter(chunks + [SimpleNamespace(choices=[])]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


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
        self.norm = EvaluationNormalizer(SIZES, max_marks=10)

    def test_answer_parts_marks_and_category(self):
        answer = self.norm.add(ANSWER)
        self.assertEqual(answer["parts"], [{"id": "q1-p1", "page": 1, "box": [50, 200, 950, 600]}])
        self.assertEqual(answer["category"], "minor_mistake")
        self.assertEqual(answer["marks_awarded"], 7.5)  # rounded to 0.5
        self.assertEqual(len(answer["marks_breakdown"]), 2)

    def test_answer_spanning_pages_is_one_answer_with_a_part_per_page(self):
        answer = self.norm.add(SPANNING)
        self.assertEqual([(p["id"], p["page"]) for p in answer["parts"]], [("q3-p1", 1), ("q3-p2", 2)])
        self.assertEqual(answer["parts"][1]["box"], [50, 40, 950, 240])

    def test_parts_on_unknown_pages_or_with_bad_boxes_are_dropped(self):
        answer = self.norm.add(dict(ANSWER, parts=[{"page": 7, "box_2d": [1, 2, 3, 4]},
                                                   {"page": 1, "box_2d": [1, 2, 3]},
                                                   {"page": 2, "box_2d": [500, 500, 500, 500]}]))
        self.assertEqual(answer["parts"], [])

    def test_single_box_answers_become_one_part(self):
        legacy = {k: v for k, v in ANSWER.items() if k != "parts"}
        answer = self.norm.add(dict(legacy, page=2, box_2d=[100, 50, 300, 950]))
        self.assertEqual([p["page"] for p in answer["parts"]], [2])

    def test_finding_links_to_answer_and_defaults_to_its_first_page(self):
        self.norm.add(dict(SPANNING, parts=SPANNING["parts"][::-1]))
        finding = self.norm.add(dict(FINDING, answer_id="q3", page=None, marks_impact=2))
        self.assertEqual((finding["answer_id"], finding["page"]), ("q3", 2))
        self.assertEqual(finding["category"], "major_mistake")
        self.assertEqual(finding["marks_impact"], -2)

    def test_duplicate_ids_are_made_unique_and_findings_follow_the_renamed_answer(self):
        self.norm.add(ANSWER)
        second = self.norm.add(dict(ANSWER, question="Q2"))
        finding = self.norm.add(dict(FINDING, answer_id="unknown"))
        self.assertEqual(second["id"], "q1-2")
        self.assertEqual(finding["answer_id"], "q1-2")  # falls back to the latest answer

    def test_marks_are_clamped_and_missing_marks_come_from_breakdown(self):
        self.assertEqual(self.norm.add(dict(ANSWER, marks_awarded=14))["marks_awarded"], 10)
        derived = self.norm.add({k: v for k, v in ANSWER.items() if k != "marks_awarded"})
        self.assertEqual(derived["marks_awarded"], 7)

    def test_finding_without_any_answer_has_no_parent(self):
        self.assertIsNone(self.norm.add(FINDING)["answer_id"])


class PromptTests(SimpleTestCase):
    def test_categories(self):
        self.assertEqual(normalize_category("Major-Mistake"), "major_mistake")
        self.assertEqual(normalize_category("not attempted"), "unattempted")
        self.assertEqual(normalize_category("???"), "minor_mistake")

    def test_max_marks_clamp_and_prompt(self):
        self.assertEqual(clamp_max_marks("abc"), 10)
        self.assertEqual(clamp_max_marks(500), 100)
        prompt = build_evaluation_prompt(5)
        self.assertIn("5 marks (the teacher's marks per question)", prompt)
        self.assertIn("never a new answer", prompt)

    def test_sheet_pages_are_numbered_and_follow_the_references(self):
        content = build_user_content([(1, "data:p1"), (2, "data:p2")], 2, ["data:ref1"], "Be strict")
        images = [c["image_url"]["url"] for c in content if c["type"] == "image_url"]
        self.assertEqual(images, ["data:ref1", "data:p1", "data:p2"])
        texts = [c.get("text", "") for c in content]
        self.assertIn("STUDENT ANSWER SHEET page 2 of 2:", texts)
        self.assertTrue(any("<<<\nBe strict\n>>>" in t for t in texts))


class GeminiStreamTests(SimpleTestCase):
    def _run(self, fn, *args, text, **kwargs):
        client, create = gemini_client(text)
        response = mock.Mock(content=png_bytes(1000, 2000), headers={"Content-Type": "image/png"})
        with mock.patch.object(ev, "OpenAI", return_value=client), \
                mock.patch.object(ev.requests, "get", return_value=response) as get, \
                mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "k"}):
            items = list(fn(*args, **kwargs))
        return items, create, get

    def test_whole_sheet_in_one_call(self):
        pages = [SheetPage(1, "https://img/p1.png", 1000, 2000), SheetPage(2, "https://img/p2.png")]
        text = "```json\n[" + json.dumps(SPANNING) + "," + json.dumps(dict(FINDING, answer_id="q3", page=2)) + "]\n```"
        items, create, get = self._run(ev.stream_evaluation, pages, "google-eval/gemini-2.5-pro",
                                       reference_urls=["https://img/key.png"], text=text)

        self.assertEqual(create.call_count, 1)
        self.assertEqual(get.call_count, 3)  # two sheet pages + the reference
        self.assertEqual([p["page"] for p in items[0]["parts"]], [1, 2])
        self.assertEqual(pages[1].width, 1000)  # missing size measured from the image
        kwargs = create.call_args.kwargs
        self.assertEqual((kwargs["model"], kwargs["stream"]), ("gemini-2.5-pro", True))
        images = [c for c in kwargs["messages"][1]["content"] if c["type"] == "image_url"]
        self.assertEqual(len(images), 3)

    def test_missing_api_key_is_reported_clearly(self):
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(ev.EvaluationError, "GOOGLE_API_KEY is not configured"):
                list(ev.stream_evaluation([SheetPage(1, "u")], "google-eval/gemini-2.5-pro"))

    def test_unknown_provider_and_page_limits_are_rejected(self):
        with self.assertRaises(ev.EvaluationError):
            ev.stream_evaluation([SheetPage(1, "u")], "openai/gpt-4o")
        with self.assertRaises(ev.EvaluationError):
            ev.stream_evaluation([], "google-eval/gemini-2.5-pro")
        with self.assertRaises(ev.EvaluationError):
            ev.stream_evaluation([SheetPage(i, "u") for i in range(1, 22)], "google-eval/gemini-2.5-pro")


class RevisionTests(SimpleTestCase):
    def setUp(self):
        norm = EvaluationNormalizer(SIZES, max_marks=10)
        self.sheet = [
            norm.add(ANSWER), norm.add(FINDING),
            norm.add(SPANNING), norm.add(dict(FINDING, id="q3-f1", answer_id="q3", page=2)),
            norm.add(dict(ANSWER, id="q4", question="Q4", parts=[{"page": 2, "box_2d": [400, 50, 600, 950]}])),
        ]

    def revision(self, **kwargs):
        return Revision(**{"feedback": "x", "previous": self.sheet, **kwargs})

    def test_targets_and_pages_follow_answers_across_pages(self):
        self.assertEqual(self.revision(scope="answer", answer_id="q3").target_ids, {"q3"})
        self.assertEqual(self.revision(scope="answer", answer_id="q3").pages_needed(2), [1, 2])
        self.assertEqual(self.revision(scope="page", page=1).target_ids, {"q1", "q3"})
        self.assertEqual(self.revision(scope="page", page=2).target_ids, {"q3", "q4"})
        self.assertEqual(self.revision(scope="page", page=2).pages_needed(2), [1, 2])  # q3 starts on page 1
        self.assertEqual(self.revision(scope="answer", answer_id="q4").pages_needed(2), [2])
        self.assertEqual(self.revision(scope="document").pages_needed(3), [1, 2, 3])

    def test_model_format_round_trips_parts(self):
        raw = ev.to_model_format(self.sheet, SIZES)
        self.assertEqual(raw[2]["parts"], SPANNING["parts"])
        self.assertEqual(raw[3]["page"], 2)
        again = EvaluationNormalizer(SIZES).add(raw[2])
        self.assertEqual([p["box"] for p in again["parts"]], [p["box"] for p in self.sheet[2]["parts"]])

    def test_answer_merge_replaces_only_that_answer_and_keeps_its_boxes(self):
        revised_answer = dict(self.sheet[2], id="q3-x", parts=[], marks_awarded=9)
        revised_finding = dict(self.sheet[3], id="q3-f9", answer_id="q3-x", comment="unit should be cm")
        merged = ev.merge_revision(self.sheet, [revised_answer, revised_finding],
                                   self.revision(scope="answer", answer_id="q3"))
        self.assertEqual([i["id"] for i in merged], ["q1", "q1-f1", "q3", "q3-f9", "q4"])
        self.assertEqual(merged[2]["parts"], self.sheet[2]["parts"])  # no boxes returned: keep both pages' boxes
        self.assertEqual(merged[3]["answer_id"], "q3")
        self.assertIs(merged[0], self.sheet[0])

    def test_answer_merge_without_a_revised_answer_is_an_error(self):
        with self.assertRaises(ev.EvaluationError):
            ev.merge_revision(self.sheet, [self.sheet[3]], self.revision(scope="answer", answer_id="q3"))

    def test_page_merge_replaces_returned_answers_keeps_omitted_ones_and_adds_new_ones(self):
        revision = self.revision(scope="page", page=2)
        new_answer = dict(self.sheet[4], id="q5", question="Q5")
        out_of_scope = dict(self.sheet[0], marks_awarded=0)
        merged = ev.merge_revision(self.sheet, [dict(self.sheet[2], marks_awarded=4), new_answer, out_of_scope],
                                   revision)
        # q3 replaced (its finding dropped: none returned), q4 left out by the model so kept, q5 added
        self.assertEqual([i["id"] for i in merged], ["q1", "q1-f1", "q3", "q4", "q5"])
        self.assertEqual(merged[2]["marks_awarded"], 4)
        self.assertIs(merged[0], self.sheet[0])  # out of scope: untouched even though returned

    def test_document_merge_keeps_answers_the_model_left_out(self):
        merged = ev.merge_revision(self.sheet, [dict(self.sheet[0], marks_awarded=2)], self.revision(scope="document"))
        self.assertEqual([i["id"] for i in merged], ["q1", "q3", "q3-f1", "q4"])
        self.assertEqual(merged[0]["marks_awarded"], 2)

    def test_revise_objects_ignores_answers_out_of_scope(self):
        revision = self.revision(scope="page", page=2)
        raw = [{"kind": "reply", "text": "Changed Q3."}, {"kind": "reply", "text": "again"},
               dict(ANSWER), dict(FINDING),                               # q1: not on page 2
               dict(SPANNING), dict(FINDING, id="q1-f1", answer_id="q3", page=2)]
        out = list(ev.revise_objects(iter(raw), SIZES, 10, revision))
        self.assertEqual(out[0], {"kind": "reply", "text": "Changed Q3."})
        self.assertEqual([o.get("id") for o in out[1:]], ["q3", "q1-f1-2"])  # q1-f1 belongs to Q1

    def test_scope_score(self):
        self.assertEqual(ev.scope_score(self.sheet, {"q1", "q3"}), (15, 20))

    def test_gemini_revision_sends_only_the_pages_it_needs(self):
        text = json.dumps([{"kind": "reply", "text": "Deducted a mark for units."}, dict(ANSWER, id="q4")])
        client, create = gemini_client(text, 9)
        response = mock.Mock(content=png_bytes(1000, 2000), headers={"Content-Type": "image/png"})
        revision = self.revision(scope="answer", answer_id="q4", feedback="Q4 unit is cm",
                                 history=[{"feedback": "be strict", "reply": "ok"}])
        pages = [SheetPage(1, "https://img/p1.png", 1000, 2000), SheetPage(2, "https://img/p2.png", 1000, 2000)]
        with mock.patch.object(ev, "OpenAI", return_value=client), \
                mock.patch.object(ev.requests, "get", return_value=response) as get, \
                mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "k"}):
            out = list(ev.stream_reevaluation(pages, "google-eval/gemini-2.5-pro", revision))

        self.assertEqual(out[0]["text"], "Deducted a mark for units.")
        self.assertEqual(get.call_args.args[0], "https://img/p2.png")  # q4 is only on page 2
        messages = create.call_args.kwargs["messages"]
        self.assertIn('ONLY the revised answer with id "q4"', messages[0]["content"])
        texts = "\n".join(c.get("text", "") for c in messages[1]["content"])
        self.assertIn("STUDENT ANSWER SHEET page 2 of 2:", texts)
        self.assertNotIn("page 1 of 2", texts)
        self.assertIn('"parts": [{"page": 1, "box_2d": [900, 50, 980, 950]}', texts)  # whole sheet as context
        self.assertIn("Teacher: be strict", texts)

    def test_revision_checks(self):
        pages = [SheetPage(1, "u"), SheetPage(2, "u")]
        for revision in (self.revision(scope="answer", answer_id="nope"), self.revision(scope="page", page=3),
                         self.revision(scope="everything")):
            with self.assertRaises(ev.EvaluationError):
                ev.stream_reevaluation(pages, "google-eval/gemini-2.5-pro", revision)
