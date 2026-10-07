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
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test", **(env or {})}), \
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
        with mock.patch.dict("os.environ", {"SARVAM_API_KEY": "sk_test"}), \
                mock.patch("httpx.stream", return_value=stream), \
                mock.patch.object(ev.requests, "get", return_value=mock.Mock(
                    content=page_png(100, 200), headers={}, raise_for_status=mock.Mock())):
            with self.assertRaisesRegex(ev.EvaluationError, r"gemma4 replied \(44 characters\), but not in the JSON"):
                list(ev.stream_evaluation([SheetPage(1, "u")], "sarvam/gemma4"))

    def test_an_empty_array_is_a_valid_answer(self):
        reply = ev._Reply(iter(["```json\n[ ]\n```"]))
        list(reply)
        ev.check_readable(reply, 0, "sarvam/gemma4")  # no error: the sheet has no answers
