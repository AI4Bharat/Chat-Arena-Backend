import json
import tempfile
from unittest import mock

from django.test import SimpleTestCase

from ai_model import evaluation_interactions as ev
from ai_model.evaluation_interactions import LineIndex, Revision, SheetPage

# Two pages; Q3 runs from the foot of page 1 onto page 2.
TRANSCRIPT = {"pages": [
    {"number": 1, "width": 1000, "height": 2000, "lines": [
        {"id": "1.1", "text": "Q1. 7 x 8 + 12", "box": [100, 100, 500, 140]},
        {"id": "1.2", "text": "= 54 + 12 = 66", "box": [120, 150, 480, 190]},
        {"id": "1.3", "text": "Q3. Cost = 3 x 45 = 135", "box": [100, 1800, 700, 1840]},
    ]},
    {"number": 2, "width": 1000, "height": 2000, "lines": [
        {"id": "2.1", "text": "Change = 200 - 135 = 75", "box": [120, 50, 650, 90]},
        {"id": "2.2", "text": "Riya gets Rs 75 back.", "box": [120, 100, 600, 140]},
    ]},
]}
SIZES = {1: (1000, 2000), 2: (1000, 2000)}


class FakeStream:
    """Stands in for httpx.stream(...): a context manager with status_code and SSE lines."""

    def __init__(self, lines=(), status_code=200, body=b""):
        self.status_code, self.lines, self.body = status_code, list(lines), body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        return iter(self.lines)

    def read(self):
        return self.body


def sse(*deltas):
    lines = [f"data: {json.dumps({'choices': [{'delta': d}]})}" for d in deltas]
    return lines + ["", "data: [DONE]"]


class PromptTests(SimpleTestCase):
    def test_guidance_comes_from_the_bundled_file_with_marks_filled_in(self):
        prompt = ev.build_evaluation_prompt(5, mode="text")
        self.assertIn("Every question is marked out of 5 marks.", prompt)
        self.assertIn("[3.12] is\npage 3, line 12", prompt)
        self.assertIn('"lines": the ids of ALL the transcript lines', prompt)
        self.assertNotIn("box_2d", prompt)
        self.assertIn('"parts"', ev.build_evaluation_prompt(5, mode="image"))

    def test_guidance_file_can_be_replaced(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("You are a strict Class 8 maths examiner. Marks: {max_marks}.")
        with mock.patch.dict("os.environ", {"EVAL_SYSTEM_PROMPT_FILE": f.name}):
            prompt = ev.build_evaluation_prompt(10, mode="text")
        self.assertTrue(prompt.startswith("You are a strict Class 8 maths examiner. Marks: 10."))
        self.assertIn("OUTPUT FORMAT", prompt)  # the contract is always appended

    def test_missing_guidance_file_is_reported(self):
        with mock.patch.dict("os.environ", {"EVAL_SYSTEM_PROMPT_FILE": "/nonexistent/prompt.md"}):
            with self.assertRaisesRegex(ev.EvaluationError, "Cannot read the evaluation system prompt"):
                ev.build_evaluation_prompt(10)


class LineIndexTests(SimpleTestCase):
    def setUp(self):
        self.index = LineIndex(TRANSCRIPT)

    def test_ids_ranges_and_loose_formats(self):
        self.assertEqual(self.index.ids(["1.1", "1.2"]), ["1.1", "1.2"])
        self.assertEqual(self.index.ids(["1.1-1.2"]), ["1.1", "1.2"])
        self.assertEqual(self.index.ids("1.1-2"), ["1.1", "1.2"])
        self.assertEqual(self.index.ids(["1.3-2.2"]), ["1.3", "2.1", "2.2"])  # across the page break
        self.assertEqual(self.index.ids(["p2 l1", "2:2", "9.9", "nonsense"]), ["2.1", "2.2"])

    def test_answer_lines_become_one_box_per_page(self):
        self.assertEqual(self.index.page_boxes(["1.3", "2.1", "2.2"]),
                         [(1, [100, 1800, 700, 1840]), (2, [120, 50, 650, 140])])

    def test_resolve_lines_for_answers_and_findings(self):
        answer = ev.resolve_lines({"kind": "answer", "id": "q3", "lines": ["1.3-2.2"]}, self.index, SIZES)
        self.assertEqual([p["page"] for p in answer["parts"]], [1, 2])
        item = ev.EvaluationNormalizer(SIZES).add(answer)
        self.assertEqual(item["parts"][1]["box"], [120, 50, 650, 140])
        finding = ev.resolve_lines({"kind": "finding", "answer_id": "q3", "lines": ["2.1"]}, self.index, SIZES)
        self.assertEqual(finding["page"], 2)
        self.assertNotIn("lines", finding)

    def test_boxes_map_back_to_lines_for_revisions(self):
        items = [{"kind": "answer", "id": "q3", "parts": [{"page": 1, "box": [90, 1790, 710, 1850]},
                                                          {"page": 2, "box": [110, 40, 660, 150]}]},
                 {"kind": "finding", "id": "f", "answer_id": "q3", "page": 2, "box": [110, 40, 660, 95]}]
        raw = ev.to_text_model_format(items, self.index)
        self.assertEqual(raw[0]["lines"], ["1.3", "2.1-2.2"])
        self.assertEqual(raw[1]["lines"], ["2.1"])
        self.assertNotIn("parts", raw[0])

    def test_default_transcription_splits_ocr_regions_into_lines(self):
        regions = [{"text": "Q1. 7 x 8 + 12\n= 54 + 12 = 66", "box": [100, 100, 500, 200]}]
        with mock.patch("ai_model.ocr_interactions.get_ocr_output", return_value=regions):
            lines = ev.ocr_transcribe_page(SheetPage(1, "https://img/p1.png"))
        self.assertEqual([ln["box"] for ln in lines], [[100, 100, 500, 150], [100, 150, 500, 200]])


class SarvamClientTests(SimpleTestCase):
    def tokens(self, stream, env=None):
        environ = {"SARVAM_API_KEY": "sk_test", **(env or {})}
        with mock.patch.dict("os.environ", environ), mock.patch("httpx.stream", return_value=stream) as call:
            text = "".join(ev._sarvam_tokens("sarvam/deepseekv4-flash", "system", "user"))
        return text, call

    def test_request_shape_and_reasoning_is_dropped(self):
        stream = FakeStream(sse({"reasoning_content": "Let me think {about braces}"},
                                {"content": "<think>inline {thoughts}</think>[{\"kind\": "},
                                {"content": "\"answer\"}]"}))
        text, call = self.tokens(stream)

        self.assertEqual(text, '[{"kind": "answer"}]')
        args, kwargs = call.call_args
        self.assertEqual(args, ("POST", "https://api.sarvam.ai/v2/chat/completions"))
        self.assertEqual(kwargs["headers"]["api-subscription-key"], "sk_test")
        self.assertNotIn("Authorization", kwargs["headers"])
        body = kwargs["json"]
        self.assertEqual((body["model"], body["stream"], body["max_tokens"]), ("deepseekv4-flash", True, 32768))
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])

    def test_base_url_and_token_budget_come_from_the_environment(self):
        _, call = self.tokens(FakeStream(sse({"content": "[]"})),
                              {"SARVAM_BASE_URL": "http://localhost:9999/v2/", "SARVAM_MAX_TOKENS": "8000"})
        self.assertEqual(call.call_args.args[1], "http://localhost:9999/v2/chat/completions")
        self.assertEqual(call.call_args.kwargs["json"]["max_tokens"], 8000)

    def test_think_tags_split_across_chunks(self):
        chunks = ["ab<thi", "nk>hidden</th", "ink>cd<think>x", "</think>e"]
        self.assertEqual("".join(ev._without_think(iter(chunks))), "abcde")

    def test_errors_are_reported_in_words(self):
        with self.assertRaisesRegex(ev.EvaluationError, r"rejected the API key \(HTTP 401\): Invalid"):
            self.tokens(FakeStream(status_code=401, body=b'{"error": {"message": "Invalid API key"}}'))
        with self.assertRaisesRegex(ev.EvaluationError, r"HTTP 400\): beta access required"):
            self.tokens(FakeStream(status_code=400, body=b'{"error": {"message": "beta access required"}}'))
        with self.assertRaisesRegex(ev.EvaluationError, "SARVAM_API_KEY is not configured"):
            with mock.patch.dict("os.environ", {"SARVAM_API_KEY": ""}):
                list(ev._sarvam_tokens("sarvam/deepseekv4-flash", "s", "u"))


class SarvamEvaluationTests(SimpleTestCase):
    MODEL_OUTPUT = json.dumps([
        {"kind": "answer", "id": "q1", "question": "Q1", "lines": ["1.1-1.2"], "category": "minor_mistake",
         "marks_awarded": 6, "max_marks": 10, "comment": "Slip in 7 x 8."},
        {"kind": "finding", "id": "q1-f1", "answer_id": "q1", "lines": ["1.2"], "category": "minor_mistake",
         "comment": "7 x 8 is 56.", "marks_impact": -1},
        {"kind": "answer", "id": "q3", "question": "Q3", "lines": ["1.3", "2.1-2.2"], "category": "minor_mistake",
         "marks_awarded": 6, "max_marks": 10, "comment": "200 - 135 is 65."},
    ])

    def run_evaluation(self, transcript=None):
        pages = [SheetPage(1, "u1", 1000, 2000), SheetPage(2, "u2", 1000, 2000)]
        lines = {1: [dict(text=ln["text"], box=ln["box"]) for ln in TRANSCRIPT["pages"][0]["lines"]],
                 2: [dict(text=ln["text"], box=ln["box"]) for ln in TRANSCRIPT["pages"][1]["lines"]]}
        stream = FakeStream(sse({"reasoning_content": "hmm"}, *[{"content": c} for c in self.MODEL_OUTPUT]))
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test"}), \
                mock.patch("httpx.stream", return_value=stream) as call, \
                mock.patch.object(ev, "transcribe_page", side_effect=lambda page, ctx=None: lines[page.number]) as ocr:
            out = list(ev.stream_evaluation(pages, "sarvam/deepseekv4-flash", instructions="Be fair",
                                            max_marks=10, transcript=transcript))
        return out, call, ocr

    def test_transcript_in_line_ids_out_boxes_per_page(self):
        out, call, ocr = self.run_evaluation()
        kinds = [o["kind"] for o in out]
        self.assertEqual(kinds[:4], ["status", "status", "transcript", "status"])
        self.assertEqual(ocr.call_count, 2)
        answers = [o for o in out if o["kind"] == "answer"]
        self.assertEqual([[p["page"] for p in a["parts"]] for a in answers], [[1], [1, 2]])
        finding = next(o for o in out if o["kind"] == "finding")
        self.assertEqual((finding["page"], finding["box"]), (1, [120, 150, 480, 190]))
        user = call.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("[2.1] Change = 200 - 135 = 75", user)
        self.assertIn("<<<\nBe fair\n>>>", user)
        self.assertIn('"lines"', call.call_args.kwargs["json"]["messages"][0]["content"])

    def test_a_kept_transcript_skips_the_ocr(self):
        out, _, ocr = self.run_evaluation(transcript=TRANSCRIPT)
        self.assertEqual(ocr.call_count, 0)
        self.assertEqual(len([o for o in out if o["kind"] == "answer"]), 2)

    def test_missing_key_fails_before_any_ocr(self):
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": ""}), \
                mock.patch.object(ev, "transcribe_page") as ocr:
            with self.assertRaises(ev.EvaluationError):
                list(ev.stream_evaluation([SheetPage(1, "u")], "sarvam/deepseekv4-flash"))
        ocr.assert_not_called()

    def test_revision_reads_the_previous_evaluation_as_lines(self):
        previous = [{"kind": "answer", "id": "q3", "question": "Q3", "marks_awarded": 6, "max_marks": 10,
                     "parts": [{"id": "q3-p1", "page": 1, "box": [90, 1790, 710, 1850]},
                               {"id": "q3-p2", "page": 2, "box": [110, 40, 660, 150]}]}]
        reply = json.dumps([{"kind": "reply", "text": "Deducted one mark."},
                            {"kind": "answer", "id": "q3", "lines": ["1.3", "2.1-2.2"], "marks_awarded": 5,
                             "max_marks": 10, "category": "minor_mistake"}])
        revision = Revision(feedback="Q3 deduct 1", scope="answer", answer_id="q3", previous=previous,
                            transcript=TRANSCRIPT)
        pages = [SheetPage(1, "u1", 1000, 2000), SheetPage(2, "u2", 1000, 2000)]
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test"}), \
                mock.patch("httpx.stream", return_value=FakeStream(sse({"content": reply}))) as call:
            out = list(ev.stream_reevaluation(pages, "sarvam/deepseekv4-flash", revision))
        self.assertEqual(out[0], {"kind": "reply", "text": "Deducted one mark."})
        self.assertEqual([p["page"] for p in out[1]["parts"]], [1, 2])
        user = call.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn('"lines": ["1.3", "2.1-2.2"]', user)
        self.assertIn('TEACHER FEEDBACK about the answer Q3 (id "q3")', user)
        self.assertIn("REVISION", call.call_args.kwargs["json"]["messages"][0]["content"])
