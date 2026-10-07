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
# Pin the OCR choice so a developer's own BODHAN_API_KEY cannot change what a test exercises.
NO_BODHAN = {"BODHAN_API_KEY": "", "EVAL_TRANSCRIPT_OCR": "", "EVAL_VISION_WITH_OCR": ""}


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
        self.assertIn("Every question is marked out of its maximum marks (see MARKS below).", prompt)
        self.assertIn("5 marks (the teacher's marks per question)", prompt)
        for section in ("\nMarks\n", "\nBoxes\n", "\nCheck before you write\n", "shown to both the teacher and the student"):
            self.assertIn(section, prompt)
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
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", **NO_BODHAN}), \
                mock.patch("httpx.stream", return_value=stream) as call, \
                mock.patch.object(ev, "transcribe_page", side_effect=lambda page, ctx=None: lines[page.number]) as ocr:
            out = list(ev.stream_evaluation(pages, "sarvam/deepseekv4-flash", instructions="Be fair",
                                            max_marks=10, transcript=transcript))
        return out, call, ocr

    def test_transcript_in_line_ids_out_boxes_per_page(self):
        out, call, ocr = self.run_evaluation()
        kinds = [o["kind"] for o in out]
        self.assertEqual(kinds[:5], ["status", "status", "status", "transcript", "status"])  # OCR x2, then the model
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
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "", **NO_BODHAN}), \
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


def page_png(width, height, seed=0):
    """A noisy page image (noise does not compress, so sizes are realistic)."""
    import io
    import random
    from PIL import Image
    rng = random.Random(seed)
    img = Image.frombytes("L", (width, height), bytes(rng.getrandbits(8) for _ in range(width * height)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


class SarvamVisionTests(SimpleTestCase):
    """Gemma 4 on Sarvam sees the page images and answers with box_2d, like Gemini."""

    MODEL_OUTPUT = "```json\n" + json.dumps([
        {"kind": "answer", "id": "q3", "question": "Q3", "category": "minor_mistake", "marks_awarded": 6,
         "max_marks": 10, "comment": "200 - 135 is 65.",
         "parts": [{"page": 1, "box_2d": [900, 50, 990, 950]}, {"page": 2, "box_2d": [20, 50, 120, 950]}]},
        {"kind": "finding", "id": "q3-f1", "answer_id": "q3", "page": 2, "box_2d": [25, 60, 45, 650],
         "category": "minor_mistake", "comment": "200 - 135 is 65, not 75.", "marks_impact": -1},
    ]) + "\n```"

    def call(self, fn, *args, env=None, stream=None, images=None, **kwargs):
        images = images or {}
        responses = lambda url, timeout=60: mock.Mock(  # noqa: E731
            content=images.get(url, page_png(100, 200)), headers={"Content-Type": "image/png"},
            raise_for_status=mock.Mock())
        stream = stream or FakeStream(sse(*[{"content": c} for c in self.MODEL_OUTPUT]))
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", **NO_BODHAN, **(env or {})}), \
                mock.patch("httpx.stream", return_value=stream) as call, \
                mock.patch.object(ev.requests, "get", side_effect=responses) as get, \
                mock.patch.object(ev, "transcribe_page") as ocr:
            out = list(fn(*args, **kwargs))
        return out, call, get, ocr

    def test_gemma_gets_the_page_images_and_no_ocr(self):
        pages = [SheetPage(1, "https://img/p1", 1000, 2000), SheetPage(2, "https://img/p2")]
        out, call, get, ocr = self.call(ev.stream_evaluation, pages, "sarvam/gemma4",
                                       reference_urls=["https://img/key"], instructions="Be fair")

        ocr.assert_not_called()
        self.assertEqual([c.args[0] for c in get.call_args_list], ["https://img/p1", "https://img/p2", "https://img/key"])
        self.assertEqual((pages[1].width, pages[1].height), (100, 200))  # measured from the image
        body = call.call_args.kwargs["json"]
        self.assertEqual((body["model"], body["stream"]), ("gemma4", True))
        self.assertEqual(call.call_args.kwargs["headers"]["api-subscription-key"], "sk_test")
        self.assertIn('"box_2d"', body["messages"][0]["content"])
        self.assertNotIn("transcript", body["messages"][0]["content"].lower())
        parts = body["messages"][1]["content"]
        images = [p["image_url"]["url"] for p in parts if p["type"] == "image_url"]
        self.assertEqual(len(images), 3)
        self.assertTrue(all(u.startswith("data:image/jpeg;base64,") for u in images))  # no remote URLs
        texts = [p["text"] for p in parts if p["type"] == "text"]
        self.assertIn("STUDENT ANSWER SHEET page 2 of 2:", texts)
        self.assertTrue(any("<<<\nBe fair\n>>>" in t for t in texts))

        self.assertEqual([o["kind"] for o in out][:2], ["status", "status"])
        answer = next(o for o in out if o["kind"] == "answer")
        self.assertEqual([(p["page"], p["box"]) for p in answer["parts"]],
                         [(1, [50, 1800, 950, 1980]), (2, [5, 4, 95, 24])])
        finding = next(o for o in out if o["kind"] == "finding")
        self.assertEqual((finding["answer_id"], finding["page"]), ("q3", 2))

    def test_other_sarvam_models_stay_text_only(self):
        self.assertTrue(ev._is_sarvam_vision("sarvam/gemma4"))
        self.assertFalse(ev._is_sarvam_vision("sarvam/deepseekv4-flash"))
        with mock.patch.dict("os.environ", {"SARVAM_VISION_MODELS": "gemma4, some-vlm"}):
            self.assertTrue(ev._is_sarvam_vision("sarvam/some-vlm"))
        with mock.patch.dict("os.environ", {"SARVAM_VISION_MODELS": ""}):
            self.assertFalse(ev._is_sarvam_vision("sarvam/gemma4"))

    def test_images_are_shrunk_to_fit_the_request_budget(self):
        from PIL import Image
        import io
        imgs = [Image.open(io.BytesIO(page_png(1200, 1700, seed=i))) for i in range(3)]
        roomy, roomy_total = ev.encode_images_within_budget(imgs, 50 * 1024 * 1024)
        tight, tight_total = ev.encode_images_within_budget(imgs, roomy_total // 3)
        self.assertLessEqual(tight_total, roomy_total // 3)
        self.assertLess(tight_total, roomy_total)
        with self.assertRaisesRegex(ev.EvaluationError, "too large to send to Sarvam"):
            ev.encode_images_within_budget(imgs, 1000)

    def test_revision_sends_only_the_pages_it_needs(self):
        previous = [{"kind": "answer", "id": "q4", "question": "Q4", "marks_awarded": 8, "max_marks": 10,
                     "parts": [{"id": "q4-p1", "page": 2, "box": [10, 400, 900, 600]}]}]
        reply = json.dumps([{"kind": "reply", "text": "Gave 9."},
                            {"kind": "answer", "id": "q4", "marks_awarded": 9, "max_marks": 10,
                             "parts": [{"page": 2, "box_2d": [200, 10, 300, 900]}]}])
        pages = [SheetPage(1, "https://img/p1", 1000, 2000), SheetPage(2, "https://img/p2", 1000, 2000)]
        revision = Revision(feedback="Q4 give 9", scope="answer", answer_id="q4", previous=previous)
        out, call, get, ocr = self.call(ev.stream_reevaluation, pages, "sarvam/gemma4", revision,
                                       stream=FakeStream(sse({"content": reply})))
        ocr.assert_not_called()
        self.assertEqual([c.args[0] for c in get.call_args_list], ["https://img/p2"])
        self.assertEqual(out[1], {"kind": "reply", "text": "Gave 9."})
        self.assertEqual(out[2]["marks_awarded"], 9)
        system = call.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("REVISION", system)
        self.assertIn("Only some sheet pages may be attached", system)
        texts = "\n".join(p.get("text", "") for p in call.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertIn('"box_2d": [200, 10, 300, 900]', texts)  # previous evaluation, in the model's own format

    def test_missing_key_and_size_errors_are_reported(self):
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": ""}), mock.patch.object(ev.requests, "get") as get:
            with self.assertRaisesRegex(ev.EvaluationError, "SARVAM_API_KEY is not configured"):
                list(ev.stream_evaluation([SheetPage(1, "u")], "sarvam/gemma4"))
        get.assert_not_called()
        with self.assertRaisesRegex(ev.EvaluationError, "larger than Sarvam accepts"):
            self.call(ev.stream_evaluation, [SheetPage(1, "u")], "sarvam/gemma4",
                     stream=FakeStream(status_code=413, body=b"too large"))
        with self.assertRaisesRegex(ev.EvaluationError, "rate limit"):
            self.call(ev.stream_evaluation, [SheetPage(1, "u")], "sarvam/gemma4",
                     stream=FakeStream(status_code=429, body=b'{"error": {"message": "slow down"}}'))


class LooseModelOutputTests(SimpleTestCase):
    """Shapes Gemma 4 actually produced on a 5-page sheet, which used to parse to nothing."""

    SIZES = {2: (1000, 2000), 3: (1000, 2000)}

    def parse(self, text):
        n = ev.EvaluationNormalizer(self.SIZES, 10)
        return [n.add(obj) for obj in ev.iter_json_objects([text])]

    def test_wrapped_objects_box_lists_and_repeated_keys(self):
        text = "```json\n" + """[
          {"answer": {"kind": "answer", "id": "q1", "question": "I", "marks_awarded": 4, "max_marks": 10,
                      "parts": [{"page": 2, "box_2d": [[100, 100, 150, 400], [300, 120, 350, 500]]}]}},
          {"answer": {"id": "q4", "question": "IV", "marks_awarded": 4, "max_marks": 10,
                      "parts": [{"page": 2, "box_2d": [[900, 100, 950, 800]],
                                 "page": 3, "box_2d": [[50, 100, 120, 800], [130, 100, 160, 300]]}]}},
          {"finding": {"answer_id": "q4", "page": 3, "box_2d": [[50, 100, 60, 200]], "comment": "c"}}
        ]""" + "\n```"
        q1, q4, finding = self.parse(text)
        self.assertEqual((q1["kind"], q1["question"]), ("answer", "I"))
        self.assertEqual([(p["page"], p["box"]) for p in q1["parts"]], [(2, [100, 200, 500, 700])])  # union
        self.assertEqual([(p["page"], p["box"]) for p in q4["parts"]],
                         [(2, [100, 1800, 800, 1900]), (3, [100, 100, 800, 320])])  # one part per repeated group
        self.assertEqual((finding["kind"], finding["answer_id"], finding["page"]), ("finding", "q4", 3))
        self.assertEqual(finding["box"], [100, 100, 200, 120])

    def test_wrapped_reply_and_wrapper_lists(self):
        objs = list(ev.iter_json_objects(['{"items": [{"reply": "Done."}, {"answer": {"id": "q1"}}]}']))
        self.assertEqual(objs, [{"kind": "reply", "text": "Done."}, {"kind": "answer", "id": "q1"}])

    def test_unreadable_reply_is_an_error_not_an_empty_evaluation(self):
        stream = FakeStream(sse({"content": "Here is my evaluation: Q1 is correct, 10/10."}))
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", **NO_BODHAN}), \
                mock.patch("httpx.stream", return_value=stream), \
                mock.patch.object(ev.requests, "get", return_value=mock.Mock(
                    content=page_png(100, 200), headers={}, raise_for_status=mock.Mock())):
            with self.assertRaisesRegex(ev.EvaluationError, r"gemma4 replied \(44 characters\), but not in the JSON"):
                list(ev.stream_evaluation([SheetPage(1, "u")], "sarvam/gemma4"))

    def test_an_empty_array_is_a_valid_answer(self):
        reply = ev._Reply(iter(["```json\n[ ]\n```"]))
        list(reply)
        ev.check_readable(reply, 0, "sarvam/gemma4")  # no error: the sheet has no answers


# Bodhan indic-ocr reply for a 1000 x 2000 page: Q3 starts at the foot of page 1.
def bodhan_reply(blocks):
    return {"id": "x", "object": "chat.completion", "choices": [{"message": {"content": "md"}}], "blocks": blocks}


PAGE1_BLOCKS = [
    {"order": 1, "label": "Paragraph", "type": "Text", "bbox_xyxy": [100, 300, 900, 500], "conf": 0.9,
     "text": "(1) b  (2) a  (3) a  (4) d"},
    {"order": 0, "label": "Page-header", "type": "Title", "bbox_xyxy": [100, 40, 900, 120], "conf": 0.9,
     "text": "Unit Test"},
    {"order": 2, "label": "Picture", "type": "Picture", "bbox_xyxy": [100, 600, 500, 900], "conf": 0.8, "text": ""},
    {"order": 3, "label": "Paragraph", "type": "Text", "bbox_xyxy": [100, 1800, 900, 1980], "conf": 0.9,
     "text": "Q3. Cost = 3 x 45 = 135"},
]
PAGE2_BLOCKS = [{"order": 0, "label": "Paragraph", "type": "Text", "bbox_xyxy": [100, 40, 900, 200], "conf": 0.9,
                 "text": "Change = 200 - 135 = 75"}]


class BodhanOcrTests(SimpleTestCase):
    def post(self, reply=None, status=200, image=None, env=None):
        response = mock.Mock(status_code=status, text="err")
        response.json = mock.Mock(return_value=reply if reply is not None else bodhan_reply(PAGE1_BLOCKS))
        image = image or page_png(1000, 2000)
        with mock.patch.dict("os.environ", {"BODHAN_API_KEY": "bk_test", **(env or {})}), \
                mock.patch.object(ev.requests, "post", return_value=response) as post, \
                mock.patch.object(ev.requests, "get", return_value=mock.Mock(
                    content=image, headers={}, raise_for_status=mock.Mock())):
            blocks = ev.bodhan_ocr_page("https://img/p1")
        return blocks, post

    def test_request_shape_and_blocks_in_reading_order(self):
        blocks, post = self.post()
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertEqual(url, "https://api.bodhan.ai/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer bk_test")
        body = kwargs["json"]
        self.assertEqual(body["model"], "indic-ocr")
        part = body["messages"][0]["content"][0]
        self.assertEqual(part["type"], "image_url")
        self.assertTrue(part["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual([b["text"] for b in blocks][:2], ["Unit Test", "(1) b  (2) a  (3) a  (4) d"])
        self.assertEqual(blocks[1]["box"], [100, 300, 900, 500])
        self.assertEqual((blocks[2]["type"], blocks[2]["text"]), ("Picture", ""))

    def test_large_pages_are_shrunk_and_boxes_scaled_back(self):
        reply = bodhan_reply([{"order": 0, "type": "Text", "bbox_xyxy": [50, 100, 450, 200], "text": "a"}])
        blocks, post = self.post(reply, image=page_png(1000, 2000), env={"BODHAN_OCR_MAX_SIDE": "1000"})
        self.assertEqual(blocks[0]["box"], [100, 200, 900, 400])  # sent at half size

    def test_errors_are_reported_in_words(self):
        err = {"error": {"message": "Invalid API key", "code": "invalid_api_key", "request_id": "r1"}}
        with self.assertRaisesRegex(ev.EvaluationError, r"Bodhan rejected the API key \(HTTP 401\): Invalid API key"):
            self.post(err, status=401)
        with self.assertRaisesRegex(ev.EvaluationError, r"Bodhan OCR error \(HTTP 502\).*request_id r2"):
            self.post({"error": {"message": "block exceeded max_tokens", "code": "x", "request_id": "r2"}}, status=502)
        with mock.patch.dict("os.environ", {"BODHAN_API_KEY": ""}):
            with self.assertRaisesRegex(ev.EvaluationError, "BODHAN_API_KEY is not configured"):
                ev.bodhan_ocr_page("u")

    def test_the_key_selects_bodhan_for_transcripts(self):
        with mock.patch.dict("os.environ", {"BODHAN_API_KEY": "bk", "EVAL_TRANSCRIPT_OCR": ""}):
            self.assertIs(ev._transcriber(), ev.bodhan_transcribe_page)
            self.assertTrue(ev.vision_with_ocr())
        with mock.patch.dict("os.environ", {"BODHAN_API_KEY": "bk", "EVAL_TRANSCRIPT_OCR": "default",
                                            "EVAL_VISION_WITH_OCR": "off"}):
            self.assertIs(ev._transcriber(), ev.transcribe_page)
            self.assertFalse(ev.vision_with_ocr())
        with mock.patch.dict("os.environ", NO_BODHAN):
            self.assertIs(ev._transcriber(), ev.transcribe_page)
            self.assertFalse(ev.vision_with_ocr())


HYBRID_TRANSCRIPT = {"pages": [
    {"number": 1, "width": 1000, "height": 2000, "lines": [
        {"id": "1.1", "text": "Unit Test", "box": [100, 40, 900, 120], "type": "Title"},
        {"id": "1.2", "text": "(1) b  (2) a  (3) a  (4) d", "box": [100, 300, 900, 500], "type": "Text"},
        {"id": "1.3", "text": "", "box": [100, 600, 500, 900], "type": "Picture"},
        {"id": "1.4", "text": "Q3. Cost = 3 x 45 = 135", "box": [100, 1800, 900, 1980], "type": "Text"}]},
    {"number": 2, "width": 1000, "height": 2000, "lines": [
        {"id": "2.1", "text": "Change = 200 - 135 = 75", "box": [100, 40, 900, 200], "type": "Text"}]},
]}


class HybridTests(SimpleTestCase):
    """Gemma 4 with Bodhan OCR: page images AND OCR blocks in, block ids out."""

    SIZES = {1: (1000, 2000), 2: (1000, 2000)}

    def setUp(self):
        self.index = LineIndex(HYBRID_TRANSCRIPT)

    def test_prompt_explains_the_blocks_and_asks_for_block_ids(self):
        prompt = ev.build_evaluation_prompt(10, mode="hybrid")
        self.assertIn('"[3.4] (Text)" is page 3', prompt)
        self.assertIn("The page image is the truth", prompt)
        self.assertIn('"blocks": the ids of ALL the OCR blocks', prompt)
        self.assertIn("Question papers with the answers written in place", prompt)  # guidance file
        self.assertIn("never put several numbered questions", prompt)
        self.assertIn("Every answer that loses marks has at least one finding", prompt)
        self.assertNotIn("{{", prompt)

    def test_answers_take_the_block_boxes_across_pages(self):
        raw = {"kind": "answer", "id": "q3", "blocks": ["1.4", "2.1"], "marks_awarded": 6}
        resolved = ev.resolve_blocks(raw, self.index, self.SIZES)
        parts = ev.EvaluationNormalizer(self.SIZES, 10).add(resolved)["parts"]
        # the blocks plus a 0.6% margin (6 px across, 12 px down on this 1000 x 2000 page)
        self.assertEqual([(p["page"], p["box"]) for p in parts], [(1, [94, 1788, 906, 1992]), (2, [94, 28, 906, 212])])

    def test_a_model_box_is_kept_only_inside_its_block(self):
        norm = ev.EvaluationNormalizer(self.SIZES, 10)
        norm.add({"kind": "answer", "id": "q1", "blocks": ["1.2"]})
        # tight box on the "(2) a" item, inside block 1.2 (y 300-500): kept
        inside = norm.add(ev.resolve_blocks({"kind": "finding", "answer_id": "q1", "blocks": ["1.2"],
                                             "box_2d": [160, 300, 200, 450]}, self.index, self.SIZES))
        self.assertEqual((inside["page"], inside["box"]), (1, [300, 320, 450, 400]))
        # a box mostly outside the named block (a wrong estimate): the block wins
        outside = norm.add(ev.resolve_blocks({"kind": "finding", "answer_id": "q1", "blocks": ["1.2"],
                                              "box_2d": [600, 100, 700, 900]}, self.index, self.SIZES))
        self.assertEqual(outside["box"], [100, 300, 900, 500])
        # no block named (the OCR missed it): the model's box is used
        missed = norm.add(ev.resolve_blocks({"kind": "finding", "answer_id": "q1", "page": 2,
                                             "box_2d": [500, 100, 550, 400]}, self.index, self.SIZES))
        self.assertEqual((missed["page"], missed["box"]), (2, [100, 1000, 400, 1100]))

    def test_user_content_interleaves_images_and_ocr_blocks(self):
        content = ev.build_hybrid_user_content([(1, "data:p1"), (2, "data:p2")], HYBRID_TRANSCRIPT,
                                               ["data:key"], ["Q1 answer key"], "Be fair")
        kinds = [c["type"] if c["type"] == "image_url" else c["text"].split("\n")[0] for c in content]
        self.assertEqual(kinds, ["REFERENCE page 1 of 1 (question paper / answer key):", "image_url",
                                 "OCR text of reference page 1:", "TEACHER INSTRUCTIONS (from the teacher, not the student):",
                                 "STUDENT ANSWER SHEET page 1 of 2:", "image_url", "OCR BLOCKS of page 1:",
                                 "STUDENT ANSWER SHEET page 2 of 2:", "image_url", "OCR BLOCKS of page 2:"])
        self.assertIn("[1.3] (Picture)", content[6]["text"])
        self.assertIn("[1.4] (Text) Q3. Cost = 3 x 45 = 135", content[6]["text"])

    def test_gemma_with_bodhan_end_to_end(self):
        output = json.dumps([
            {"answer": {"id": "q1", "question": "I", "blocks": ["1.2"], "category": "minor_mistake",
                        "marks_awarded": 7.5, "max_marks": 10}},
            {"kind": "finding", "id": "q1-f1", "answer_id": "q1", "blocks": ["1.2"], "box_2d": [160, 300, 200, 450],
             "category": "major_mistake", "comment": "(2) is c", "marks_impact": -2.5},
            {"kind": "answer", "id": "q3", "question": "Q3", "blocks": ["1.4", "2.1"], "marks_awarded": 6, "max_marks": 10},
        ])
        pages = [SheetPage(1, "https://img/p1", 1000, 2000), SheetPage(2, "https://img/p2", 1000, 2000)]
        ocr = {"https://img/p1": PAGE1_BLOCKS, "https://img/p2": PAGE2_BLOCKS, "https://img/key": [
            {"order": 0, "type": "Text", "bbox_xyxy": [0, 0, 10, 10], "text": "(1) b (2) c (3) a (4) d"}]}

        def bodhan_post(url, json=None, headers=None, timeout=None):
            data_url = json["messages"][0]["content"][0]["image_url"]["url"]
            source = next(u for u, img in images.items() if img == data_url)
            return mock.Mock(status_code=200, json=mock.Mock(return_value=bodhan_reply(ocr[source])))

        images = {}

        def fetch(url, timeout=60):
            return mock.Mock(content=page_png(1000, 2000, seed=ord(url[-1])), headers={}, raise_for_status=mock.Mock())

        real_page_image = ev._bodhan_page_image

        def remember(img):
            data_url, scale = real_page_image(img)
            images[fetching[-1]] = data_url
            return data_url, scale

        fetching = []
        real_fetch = ev._fetch_image

        def fetch_image(url):
            fetching.append(url)
            return real_fetch(url)

        stream = FakeStream(sse(*[{"content": c} for c in output]))
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", "BODHAN_API_KEY": "bk_test",
                                            "EVAL_TRANSCRIPT_OCR": "", "EVAL_VISION_WITH_OCR": "",
                                            "BODHAN_OCR_CONCURRENCY": "1"}), \
                mock.patch.object(ev.requests, "get", side_effect=fetch), \
                mock.patch.object(ev.requests, "post", side_effect=bodhan_post) as post, \
                mock.patch.object(ev, "_fetch_image", side_effect=fetch_image), \
                mock.patch.object(ev, "_bodhan_page_image", side_effect=remember), \
                mock.patch("httpx.stream", return_value=stream) as call:
            out = list(ev.stream_evaluation(pages, "sarvam/gemma4", reference_urls=["https://img/key"]))

        self.assertEqual(post.call_count, 3)  # two sheet pages + the answer key
        transcript = next(o for o in out if o["kind"] == "transcript")["transcript"]
        self.assertEqual([ln["id"] for ln in transcript["pages"][0]["lines"]], ["1.1", "1.2", "1.3", "1.4"])
        self.assertEqual(transcript["reference_texts"], ["(1) b (2) c (3) a (4) d"])  # kept for revisions
        body = call.call_args.kwargs["json"]
        self.assertEqual(body["model"], "gemma4")
        self.assertIn("OCR BLOCKS", body["messages"][0]["content"])
        texts = "\n".join(p.get("text", "") for p in body["messages"][1]["content"])
        self.assertIn("[2.1] (Text) Change = 200 - 135 = 75", texts)
        self.assertIn("OCR text of reference page 1:\n(1) b (2) c (3) a (4) d", texts)
        self.assertEqual(sum(p["type"] == "image_url" for p in body["messages"][1]["content"]), 3)

        answers = {o["id"]: o for o in out if o["kind"] == "answer"}
        self.assertEqual([(p["page"], p["box"]) for p in answers["q3"]["parts"]],
                         [(1, [94, 1788, 906, 1992]), (2, [94, 28, 906, 212])])
        finding = next(o for o in out if o["kind"] == "finding")
        self.assertEqual(finding["box"], [300, 320, 450, 400])

    def test_revision_reuses_the_kept_transcript_and_sends_block_ids(self):
        previous = [{"kind": "answer", "id": "q3", "question": "Q3", "marks_awarded": 6, "max_marks": 10,
                     "parts": [{"id": "q3-p1", "page": 1, "box": [100, 1800, 900, 1980]},
                               {"id": "q3-p2", "page": 2, "box": [100, 40, 900, 200]}]}]
        reply = json.dumps([{"kind": "reply", "text": "Q3 deserves 5."},
                            {"kind": "answer", "id": "q3", "blocks": ["1.4", "2.1"], "marks_awarded": 5, "max_marks": 10}])
        revision = Revision(feedback="Q3 deduct 1", scope="answer", answer_id="q3", previous=previous,
                            transcript={**HYBRID_TRANSCRIPT, "reference_texts": ["(1) b (2) c"]})
        pages = [SheetPage(1, "https://img/p1", 1000, 2000), SheetPage(2, "https://img/p2", 1000, 2000)]
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", "BODHAN_API_KEY": "bk_test",
                                            "EVAL_TRANSCRIPT_OCR": "", "EVAL_VISION_WITH_OCR": ""}), \
                mock.patch.object(ev.requests, "get", return_value=mock.Mock(
                    content=page_png(100, 200), headers={}, raise_for_status=mock.Mock())), \
                mock.patch.object(ev.requests, "post") as post, \
                mock.patch("httpx.stream", return_value=FakeStream(sse({"content": reply}))) as call:
            out = list(ev.stream_reevaluation(pages, "sarvam/gemma4", revision, reference_urls=["https://img/key"]))
        post.assert_not_called()  # no OCR at all: sheet and answer key were kept from the first run
        self.assertEqual(next(o for o in out if o["kind"] == "reply")["text"], "Q3 deserves 5.")
        answer = next(o for o in out if o["kind"] == "answer")
        self.assertEqual([p["page"] for p in answer["parts"]], [1, 2])
        texts = "\n".join(p.get("text", "") for p in call.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertIn('"blocks": ["1.4", "2.1"]', texts)
        self.assertIn("OCR text of reference page 1:\n(1) b (2) c", texts)
        self.assertIn("REVISION", call.call_args.kwargs["json"]["messages"][0]["content"])


class MarksScalingTests(SimpleTestCase):
    def add(self, **raw):
        return ev.EvaluationNormalizer({1: (1000, 2000)}, None).add({"kind": "answer", "id": "q1", **raw})

    def test_a_distribution_on_another_scale_is_scaled_to_max_marks(self):
        # a correct 1-mark item the model left at 2.5 of 2.5 (with marks_awarded = the unscaled sum)
        a = self.add(max_marks=1, marks_awarded=2.5, marks_breakdown=[{"criterion": "Correct option", "awarded": 2.5, "max": 2.5}])
        self.assertEqual((a["marks_awarded"], a["marks_breakdown"][0]["max"]), (1, 1))
        # three true/false parts at 3.5 each (10.5 in all), two right, on a 10-mark question
        b = self.add(max_marks=10, marks_awarded=7, marks_breakdown=[{"criterion": f"({i})", "awarded": v, "max": 3.5}
                                                                     for i, v in enumerate((3.5, 3.5, 0))])
        self.assertEqual(b["marks_awarded"], 6.5)
        self.assertEqual(sum(r["max"] for r in b["marks_breakdown"]), 9.99)

    def test_a_scaled_marks_awarded_and_a_correct_distribution_are_kept(self):
        a = self.add(max_marks=10, marks_awarded=10, marks_breakdown=[{"criterion": "x", "awarded": 2.5, "max": 2.5}])
        self.assertEqual(a["marks_awarded"], 10)  # already scaled by the model
        b = self.add(max_marks=10, marks_awarded=7, marks_breakdown=[{"criterion": "x", "awarded": 4, "max": 5},
                                                                     {"criterion": "y", "awarded": 3, "max": 5}])
        self.assertEqual((b["marks_awarded"], b["marks_breakdown"][0]["awarded"]), (7, 4))


class MarksFromThePaperTests(SimpleTestCase):
    def test_blank_marks_mean_from_the_paper(self):
        self.assertIsNone(ev.marks_setting(None))
        self.assertIsNone(ev.marks_setting(""))
        self.assertIsNone(ev.marks_setting("  "))
        self.assertEqual(ev.marks_setting("5"), 5)
        self.assertEqual(ev.marks_setting(500), 100)

    def test_prompt_takes_marks_from_the_paper_then_the_input(self):
        auto = ev.build_evaluation_prompt(None, mode="hybrid")
        self.assertIn('"4X1=4" (four questions\nof 1 mark each)', auto)
        self.assertIn('"max_marks": this question\'s maximum marks (see MARKS)', auto)
        self.assertIn("Only when the paper gives a question no marks, take them from the input: the marks the TEACHER\n"
                      "INSTRUCTIONS give", auto)
        self.assertIn("use\n10 marks.", auto)
        self.assertIn("Every question is marked out of its maximum marks (see MARKS below).", auto)  # guidance
        self.assertNotIn("{max_marks}", auto)
        teacher = ev.build_evaluation_prompt(5, mode="hybrid")
        self.assertIn("use\n5 marks (the teacher's marks per question).", teacher)
        self.assertIn('"max_marks": this question\'s maximum marks (see MARKS)', teacher)

    def test_each_answer_keeps_its_own_maximum(self):
        n = ev.EvaluationNormalizer({1: (1000, 2000)}, None)
        one = n.add({"kind": "answer", "id": "q1", "marks_awarded": 1, "max_marks": 1})
        three = n.add({"kind": "answer", "id": "q2", "marks_awarded": 4, "max_marks": 3})  # clamped to its max
        from_rows = n.add({"kind": "answer", "id": "q3", "marks_awarded": 1.5,
                           "marks_breakdown": [{"criterion": "a", "awarded": 1, "max": 1}, {"criterion": "b", "awarded": 0.5, "max": 1}]})
        nothing = n.add({"kind": "answer", "id": "q4", "marks_awarded": 6})
        self.assertEqual([(a["marks_awarded"], a["max_marks"]) for a in (one, three, from_rows, nothing)],
                         [(1, 1), (3, 3), (1.5, 2), (6, 10)])
        finding = n.add({"kind": "finding", "answer_id": "q1", "marks_impact": -4})
        self.assertEqual(finding["marks_impact"], -1)  # no more than its answer's maximum

    def test_the_paper_wins_and_the_teachers_number_fills_in(self):
        n = ev.EvaluationNormalizer({1: (1000, 2000)}, 5)
        from_paper = n.add({"kind": "answer", "id": "q1", "marks_awarded": 1, "max_marks": 1,
                            "marks_breakdown": [{"criterion": "Correct option", "awarded": 1, "max": 1}]})
        no_marks = n.add({"kind": "answer", "id": "q2", "marks_awarded": 4})
        self.assertEqual([(a["marks_awarded"], a["max_marks"]) for a in (from_paper, no_marks)], [(1, 1), (4, 5)])


# A worksheet page: printed questions, and answers 05-07 that the OCR merged into one block.
WORKSHEET = {"pages": [{"number": 2, "width": 1000, "height": 2000, "lines": [
    {"id": "2.1", "text": "II. Match the following. 4X1=4", "box": [100, 900, 900, 940], "type": "Text"},
    {"id": "2.2", "text": "05. FIVB first president\n06. positive emotion\n07. British hockey union",
     "box": [150, 1000, 800, 1150], "type": "Text"},
    {"id": "2.3", "text": "08. Bengal", "box": [150, 1160, 450, 1200], "type": "Text"},
    {"id": "2.4", "text": "13. What are emotions?", "box": [100, 1300, 600, 1330], "type": "Text"},
    {"id": "2.5", "text": "Feelings like joy and fear", "box": [150, 1340, 900, 1400], "type": "Text"},
]}]}


class OneBoxPerQuestionTests(SimpleTestCase):
    SIZES = {2: (1000, 2000)}

    def setUp(self):
        self.resolver = ev.HybridResolver(ev.LineIndex(WORKSHEET), self.SIZES)
        self.normalizer = ev.EvaluationNormalizer(self.SIZES, None)

    def box(self, raw):
        item = self.normalizer.add(self.resolver.resolve(raw))
        return item["parts"][0]["box"] if item["kind"] == "answer" else item["box"]

    def test_a_merged_block_is_cut_to_each_questions_line(self):
        boxes = [self.box({"kind": "answer", "id": f"q{n}", "question": f"0{n}", "blocks": ["2.2"], "max_marks": 1})
                 for n in (5, 6, 7)]
        # each question's lines, plus the 6/12 px margin
        self.assertEqual(boxes, [[144, 988, 806, 1062], [144, 1038, 806, 1112], [144, 1088, 806, 1162]])
        self.assertEqual(self.box({"kind": "answer", "id": "q8", "question": "08", "blocks": ["2.3"]}),
                         [144, 1148, 456, 1212])  # its own block, not cut

    def test_slicing_only_applies_to_merged_numbered_blocks(self):
        self.assertIsNone(ev.slice_for_question([0, 0, 10, 10], "Feelings like joy", 13))
        self.assertIsNone(ev.slice_for_question([0, 0, 10, 10], "05. a\n06. b", 9))  # number not in it
        self.assertIsNone(ev.slice_for_question([0, 0, 10, 10], "<table><tr><td>05.</td></tr></table>", 5))
        self.assertEqual(ev.slice_for_question([0, 0, 10, 40], "header\n05. a\n06. b\nmore of b", 6), [0, 20, 10, 40])

    def test_a_finding_stays_inside_its_questions_slice(self):
        self.box({"kind": "answer", "id": "q6", "question": "06", "blocks": ["2.2"]})
        finding = self.box({"kind": "finding", "answer_id": "q6", "blocks": ["2.2"]})
        self.assertEqual(finding, [150, 1038, 800, 1112])  # the block, inside q6's box


class NestedFindingsAndRedoTests(SimpleTestCase):
    def objects(self, text):
        return list(ev.settle_answers(ev.iter_json_objects([text])))

    def test_findings_nested_in_their_answer_come_out_after_it(self):
        out = self.objects('[{"kind": "answer", "id": "q13", "question": "13", "marks_awarded": 0, "findings": ['
                           '{"id": "q13-f1", "blocks": ["3.3"], "marks_impact": -1}]},'
                           '{"answer": {"id": "q14", "question": "14", "findings": [{"kind": "finding", "id": "f"}]}},'
                           '{"kind": "finding", "id": "q14-f2", "answer_id": "q14"}]')
        self.assertEqual([(o["kind"], o["id"], o.get("answer_id")) for o in out],
                         [("answer", "q13", None), ("finding", "q13-f1", "q13"),
                          ("answer", "q14", None), ("finding", "f", "q14"), ("finding", "q14-f2", "q14")])
        self.assertNotIn("findings", out[0])

    def test_an_answer_the_model_redoes_is_replaced_with_its_findings(self):
        out = self.objects('[{"kind": "answer", "id": "q16", "question": "16", "blocks": ["3.9"], "marks_awarded": 0,'
                           ' "comment": "Wait, the image shows 1947. Let\'s re-evaluate.",'
                           ' "findings": [{"id": "q16-f1", "marks_impact": -1}]},'
                           '{"kind": "answer", "id": "q16_revised", "question": "16", "blocks": ["3.9"], "marks_awarded": 1},'
                           '{"kind": "answer", "id": "q17", "question": "17", "blocks": ["3.12"]}]')
        self.assertEqual([o["id"] for o in out], ["q16_revised", "q17"])

    def test_same_label_elsewhere_is_a_different_question(self):
        # The sheet prints "22." twice; the second is a different question at a different place.
        out = self.objects('[{"kind": "answer", "id": "q22", "question": "22", "blocks": ["4.6"]},'
                           '{"kind": "answer", "id": "q24", "question": "22", "blocks": ["4.10"]},'
                           '{"kind": "answer", "id": "q24_final", "question": "22", "blocks": ["4.9", "4.10"]},'
                           '{"kind": "answer", "id": "a", "blocks": ["5.1"]}, {"kind": "answer", "id": "b", "blocks": ["5.1"]}]')
        self.assertEqual([o["id"] for o in out], ["q22", "q24_final", "a", "b"])  # unlabeled: never merged

    def test_contract_nests_findings_and_asks_for_them_where_marks_are_lost(self):
        for mode in ("image", "text", "hybrid"):
            prompt = ev.build_evaluation_prompt(None, mode=mode)
            self.assertIn('each answer carries its own "finding" objects in its "findings" list', prompt)
            self.assertIn('"findings": [{"kind": "finding", "id": "q13-f1"', prompt)
            self.assertIn('"findings": []}]', prompt)
        self.assertIn("each with a finding for every place where it lost marks", ev.EVALUATE_REQUEST)
        self.assertTrue(ev.build_text_user_content({"pages": []}, "", "").endswith(ev.EVALUATE_REQUEST))


class TeacherAndStudentCommentTests(SimpleTestCase):
    def test_working_and_input_talk_are_dropped_from_comments(self):
        comment = ("The student wrote 1947, but FIVB was founded in 1947. Wait, looking at the image, the student "
                   "wrote 1947. The OCR says 1967 1947. The image shows 1947. This is correct. Let's re-evaluate. "
                   "Block [3.9] holds it.")
        self.assertEqual(ev.polish_comment(comment, 2000), "The student wrote 1947, but FIVB was founded in 1947. This is correct.")

    def test_ordinary_feedback_is_kept(self):
        comment = "Correctly labels the parts of the image. Re-check the units in step 2. Did not follow the instructions."
        self.assertEqual(ev.polish_comment(comment, 2000), comment)
        self.assertEqual(ev.polish_comment("Wait.", 2000), "Wait.")  # nothing else to show: kept as it is

    def test_comments_are_polished_and_the_ocr_check_is_kept_for_the_teacher(self):
        n = ev.EvaluationNormalizer({1: (1000, 2000)}, None)
        a = n.add({"kind": "answer", "id": "q1", "max_marks": 1, "marks_awarded": 1, "ocr_check": "OCR read '1967'; the sheet shows '1947'",
                   "comment": "Correct year. Wait, the OCR says 1967."})
        f = n.add({"kind": "finding", "answer_id": "q1", "comment": "Let me check. Spelling of 'volleyball' is wrong.", "marks_impact": 0})
        self.assertEqual((a["comment"], a["ocr_check"]), ("Correct year.", "OCR read '1967'; the sheet shows '1947'"))
        self.assertEqual(f["comment"], "Spelling of 'volleyball' is wrong.")
        self.assertNotIn("ocr_check", n.add({"kind": "answer", "id": "q2"}))

    def test_hybrid_contract_asks_for_the_ocr_check_and_whole_answer_boxes(self):
        hybrid = ev.build_evaluation_prompt(None, mode="hybrid")
        self.assertIn('- "ocr_check": "ok" when the OCR text of this answer matches', hybrid)
        self.assertIn("Verify the OCR before you rely on it", hybrid)
        self.assertIn("never leave a block out to make the box smaller", hybrid)
        self.assertNotIn("ocr_check", ev.build_evaluation_prompt(None, mode="image"))
        self.assertIn("never cuts through the student's writing", ev.build_evaluation_prompt(None, mode="image"))


class WholeAnswerBoxTests(SimpleTestCase):
    SIZES = {2: (1000, 2000)}

    def resolve(self, raw):
        return ev.EvaluationNormalizer(self.SIZES, None).add(ev.HybridResolver(ev.LineIndex(WORKSHEET), self.SIZES).resolve(raw))

    def test_a_model_box_inside_the_blocks_never_trims_the_answer(self):
        item = self.resolve({"kind": "answer", "id": "q13", "question": "13", "blocks": ["2.5"],
                             "parts": [{"page": 2, "box_2d": [672, 200, 690, 500]}]})  # a sliver inside 2.5
        self.assertEqual([p["box"] for p in item["parts"]], [[144, 1328, 906, 1412]])  # all of 2.5, plus margin

    def test_writing_the_ocr_missed_becomes_its_own_part(self):
        item = self.resolve({"kind": "answer", "id": "q13", "question": "13", "blocks": ["2.5"],
                             "parts": [{"page": 2, "box_2d": [710, 100, 740, 400]}]})  # below 2.5, no block
        self.assertEqual([p["box"] for p in item["parts"]], [[144, 1328, 906, 1412], [100, 1420, 400, 1480]])

    def test_an_answer_without_a_location_gets_its_printed_question(self):
        item = self.resolve({"kind": "answer", "id": "q6", "question": "06", "category": "unattempted"})
        self.assertEqual([p["box"] for p in item["parts"]], [[144, 1038, 806, 1112]])  # question 06's line of 2.2


class ReviewFlagTests(SimpleTestCase):
    def add(self, **raw):
        return ev.EvaluationNormalizer({1: (1000, 2000)}, None).add({"kind": "answer", "id": "q1", "max_marks": 1, **raw})

    def test_an_answer_the_model_reconsidered_is_flagged(self):
        a = self.add(marks_awarded=0, category="major_mistake",
                     comment="The student wrote 1947. Wait, looking at the image, 1947 is right. This is correct.")
        self.assertEqual(a["comment"], "The student wrote 1947. This is correct.")
        self.assertEqual(a["review"], [ev.REVIEW_RECONSIDERED])

    def test_category_and_marks_that_disagree_are_flagged(self):
        self.assertEqual(self.add(marks_awarded=0.5, category="correct")["review"], [ev.REVIEW_CATEGORY_MARKS])
        self.assertEqual(self.add(marks_awarded=1, category="major_mistake")["review"], [ev.REVIEW_CATEGORY_MARKS])

    def test_a_consistent_answer_is_not_flagged(self):
        self.assertNotIn("review", self.add(marks_awarded=1, category="correct", comment="Correct year."))
        # only input talk was dropped (no change of mind): not flagged
        self.assertNotIn("review", self.add(marks_awarded=0, category="major_mistake", comment="Wrong year. The OCR read 1967."))


class WholePromptFileTests(SimpleTestCase):
    """EVAL_SYSTEM_PROMPT_FILE may hold the whole rendered prompt instead of the guidance alone."""

    def setUp(self):
        with mock.patch.dict("os.environ", {"EVAL_SYSTEM_PROMPT_FILE": ""}):
            self.whole = ev.build_evaluation_prompt(None, mode="hybrid") + "\n"
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write(self.whole.replace("Write plainly, specifically and kindly", "Write plainly and kindly"))  # an edit
        f.close()
        self.env = mock.patch.dict("os.environ", {"EVAL_SYSTEM_PROMPT_FILE": f.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_gemma_with_bodhan_gets_the_file_as_it_is(self):
        prompt = ev.build_evaluation_prompt(None, mode="hybrid")
        self.assertEqual(prompt.count("OUTPUT FORMAT"), 1)
        self.assertIn("Write plainly and kindly", prompt)
        self.assertEqual(prompt, self.whole.strip().replace("Write plainly, specifically and kindly", "Write plainly and kindly"))

    def test_the_teachers_marks_go_into_its_marks_fallback(self):
        prompt = ev.build_evaluation_prompt(5, mode="hybrid")
        self.assertIn("use\n5 marks (the teacher's marks per question).", prompt)
        self.assertNotIn("use\n10 marks.", prompt)

    def test_other_models_take_its_guidance_with_their_own_format(self):
        for mode, location in (("text", '"lines": the ids'), ("image", '"parts": the boxes')):
            prompt = ev.build_evaluation_prompt(None, mode=mode)
            self.assertEqual(prompt.count("OUTPUT FORMAT"), 1, mode)
            self.assertIn("Write plainly and kindly", prompt)
            self.assertIn(location, prompt)
            self.assertNotIn("OCR BLOCKS", prompt)

    def test_a_revision_appends_to_the_file(self):
        revision = ev.Revision(feedback="Q2: give 1", scope="answer", answer_id="q2")
        prompt = ev.build_revision_prompt(None, revision, mode="hybrid")
        self.assertEqual(prompt.count("OUTPUT FORMAT"), 1)
        self.assertIn("REVISION", prompt)
