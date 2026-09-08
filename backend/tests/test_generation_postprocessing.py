import sys
import unicodedata
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules.generation.postprocessing import (  # noqa: E402
    contains_exact_text,
    filter_duplicate_questions,
    question_fingerprint,
    validate_source_grounding,
    validate_true_false_clarity,
    contains_source_keyword,
    find_source_span,
    validate_question_quality,
)
from modules.questions.contracts import validate_question_contract
from modules.generation.schemas import GeneratedQuestion  # noqa: E402


CONTEXT = """
Mục lục: [Ngăn xếp]
Nội dung: Ngăn xếp (Stack) là cấu trúc dữ liệu tuân theo nguyên tắc LIFO (Last In First Out).
""".strip()


def candidate(**overrides):
    item = {
        "question": "Ngăn xếp (Stack) tuân theo nguyên tắc FIFO.",
        "options": {"A": "Đúng", "B": "Sai"},
        "correct_answer": "B",
        "explanation": "Ngăn xếp dùng LIFO, không phải FIFO.",
        "question_type": "dung_sai",
        "bloom_level": "2_hieu",
        "difficulty": "trung_binh",
        "source_context": (
            "Ngăn xếp (Stack) là cấu trúc dữ liệu tuân theo nguyên tắc "
            "LIFO (Last In First Out)."
        ),
        "source_keywords": ["Ngăn xếp (Stack)"],
        "false_mutation": {
            "field": "relation",
            "original": "LIFO",
            "replacement": "FIFO",
        },
    }
    item.update(overrides)
    return item


class GenerationPostProcessingTests(unittest.TestCase):
    def test_keyword_tolerates_se_and_punctuation_but_preserves_meaning(self):
        self.assertTrue(contains_source_keyword("Giải thuật sẽ kết thúc.", "giải thuật kết thúc"))
        self.assertTrue(contains_source_keyword("Ngăn xếp (Stack)", "Ngăn xếp Stack"))
        for phrase in ("giải thuật không kết thúc", "giai thuat kết thúc", "giải thuật kết thúc sau 2 bước"):
            self.assertFalse(contains_source_keyword("Giải thuật kết thúc sau 3 bước.", phrase))
        self.assertFalse(contains_source_keyword("Heapsort", "heap"))
        self.assertFalse(contains_source_keyword("sẽ", "sẽ"))

    def test_quote_alignment_preserves_original_unicode_offsets_and_semantics(self):
        original = "Mở đầu. " + unicodedata.normalize("NFD", "GIẢI THUẬT n ày, kết thúc.")
        span = find_source_span(original, "Giải thuật nà y kết thúc.")
        self.assertIsNotNone(span)
        self.assertEqual(original[slice(*span)], unicodedata.normalize("NFD", "GIẢI THUẬT n ày, kết thúc."))
        for quote in ("giải thuật không kết thúc", "giải thuật này sẽ kết thúc", "giai thuat nay kết thúc"):
            self.assertIsNone(find_source_span(original, quote))
        for source, quote in (("Heapsort", "heap"), ("a > b", "a < b"), ("x = 1.5", "x = 15"), ("C++", "C--"), ("a*(b+c)", "a*b+c"), ("x = 1,5", "x = 15")):
            self.assertIsNone(find_source_span(source, quote))

    def test_quote_alignment_ignores_only_ocr_list_presentation(self):
        original = (
            '• Tính phổ dụng: Giải thuật phải "vét\' hết các trường hợp.\n'
            "o Thực hiện nhanh, tốn ít thời gian.\n"
            "o Tiêu phí ít tài nguyên của máy."
        )
        quote = (
            "• Tính phổ dụng: Giải thuật phải vét hết các trường hợp.\n"
            "Thực hiện nhanh, tốn ít thời gian.\n"
            "Tiêu phí ít tài nguyên của máy."
        )

        span = find_source_span(original, quote)

        self.assertEqual(
            original[slice(*span)],
            original.removeprefix("• "),
        )
        self.assertIsNone(find_source_span("sort()", "srt()"))

    def test_bank_contract_rejects_duplicate_choices(self):
        for kind in ("trac_nghiem", "tinh_huong", "nhieu_lua_chon"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "trùng nội dung"):
                validate_question_contract("Chọn đáp án", kind, {
                    "options": {"A": "Tính xác định.", "B": "Tính kết thúc", "C": " TÍNH   XÁC ĐỊNH! ", "D": "Giao diện"},
                    "correct_answer": "A,C" if kind == "nhieu_lua_chon" else "A",
                })
        validate_question_contract("Chọn biểu thức", "trac_nghiem", {
            "options": {"A": "a > b", "B": "a < b", "C": "a >= b", "D": "a <= b"}, "correct_answer": "A",
        })

    def test_multi_select_requires_two_correct_and_one_incorrect(self):
        options = {"D": "Bốn", "C": "Ba", "A": "Một", "B": "Hai"}
        for answer in ("A", "A,A", "A,B,C,D", "A,Z"):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                validate_question_contract("Chọn nhiều", "nhieu_lua_chon", {"options": options, "correct_answer": answer})
        _, data = validate_question_contract("Chọn nhiều", "nhieu_lua_chon", {"options": options, "correct_answer": "A,C"})
        self.assertEqual(data["correct_answer"], "A,C")

    def test_matching_rejects_distractor_repeating_answer_clause(self):
        item = candidate(
            question_type="ghep_cot",
            options={
                "1": "Tính kết thúc",
                "2": "Tính xác định",
                "3": "Tính phổ dụng",
                "A": "Giải thuật phải dừng sau một số hữu hạn bước.",
                "B": "Các máy tính thực hiện cùng bước phải cho cùng kết quả.",
                "C": "Giải thuật áp dụng cho một loạt bài toán cùng loại.",
                "D": "Trong trường hợp xấu nhất, giải thuật phải dừng.",
            },
            correct_answer="1-A,2-B,3-C",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="ghep_cot", candidate_index=1,
            )
        }

        self.assertIn("MATCHING_DISTRACTOR_OVERLAPS_ANSWER", codes)

    def test_matching_requires_instruction_and_grounded_descriptions(self):
        source = (
            "Ngăn xếp là cấu trúc LIFO. "
            "Hàng đợi là cấu trúc FIFO. "
            "Cây là cấu trúc phân cấp."
        )
        item = candidate(
            question="Đặc trưng nào phù hợp với các cấu trúc dữ liệu?",
            question_type="ghep_cot",
            source_context=source,
            options={
                "1": "Ngăn xếp",
                "2": "Hàng đợi",
                "3": "Cây",
                "A": "Vì cấu trúc LIFO.",
                "B": "Vì cấu trúc FIFO.",
                "C": "Mô tả không có trong nguồn.",
                "D": "Cấu trúc tuần tự.",
            },
            correct_answer="1-A,2-B,3-C",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="ghep_cot", candidate_index=1,
            )
        }

        self.assertIn("MATCHING_INSTRUCTION_MISSING", codes)
        self.assertIn("MATCHING_DESCRIPTION_UNGROUNDED", codes)

    def test_multi_select_rejects_bare_term_as_correct_option(self):
        item = candidate(
            question="Chọn tất cả đáp án đúng: Đặc trưng nào phù hợp?",
            question_type="nhieu_lua_chon",
            source_context="Tính kết thúc và tính xác định là hai đặc trưng.",
            options={
                "A": "Tính kết thúc",
                "B": "Tính xác định",
                "C": "Tính ngẫu nhiên",
                "D": "Tính vô hạn",
            },
            correct_answer="A,B",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="nhieu_lua_chon", candidate_index=1,
            )
        }

        self.assertIn("MULTIPLE_RESPONSE_CORRECT_OPTION_TOO_SHORT", codes)

    def test_ordering_checks_source_sequence_not_just_answer_permutation(self):
        source = "Bước 1: Nhập a và b. Bước 2: Tính tổng s = a + b. Bước 3: In s. Bước 4: Kết thúc."
        item = candidate(question_type="sap_xep", source_context=source, options={
            "1": "In s.", "2": "Kết thúc.", "3": "Nhập a và b.", "4": "Tính tổng s = a + b.",
        }, correct_answer="3,4,1,2")
        self.assertEqual(validate_question_quality(item, question_type="sap_xep", candidate_index=1), [])
        bullet_source = source.replace(" Bước", "\n\no Bước")
        self.assertEqual(validate_question_quality({**item, "source_context": bullet_source}, question_type="sap_xep", candidate_index=1), [])
        for updates, code in (
            ({"correct_answer": "2,4,3,1"}, "ORDERING_INCORRECT"),
            ({"source_context": "Giải thuật có tính kết thúc."}, "ORDERING_SOURCE_UNVERIFIABLE"),
            ({"source_context": source + " Quay lại bước 2."}, "ORDERING_SOURCE_UNVERIFIABLE"),
            ({"source_context": source + " Nếu hợp lệ thì thực hiện bước 3."}, "ORDERING_SOURCE_UNVERIFIABLE"),
            ({"options": {**item["options"], "4": "Lấy a chia dư cho b."}}, "ORDERING_STEP_NOT_GROUNDED"),
            ({"options": {**item["options"], "4": "Tính tổng s"}}, "ORDERING_STEP_NOT_GROUNDED"),
        ):
            errors = validate_question_quality({**item, **updates}, question_type="sap_xep", candidate_index=1)
            self.assertIn(code, {error.code for error in errors})

    def test_scenario_and_fill_blank_quality(self):
        errors = validate_question_quality(candidate(question_type="tinh_huong", question="Giải thuật là gì?"), question_type="tinh_huong", candidate_index=1)
        self.assertIn("SCENARIO_INCOMPLETE", {error.code for error in errors})
        self.assertEqual(validate_question_quality(candidate(
            question_type="tinh_huong", question="Một lập trình viên đang xây chức năng hoàn tác thao tác gần nhất. Bạn nên chọn cấu trúc dữ liệu nào?",
        ), question_type="tinh_huong", candidate_index=1), [])
        errors = validate_question_quality(candidate(question_type="dien_khuyet", question="Nguyên tắc LIFO còn được gọi là _____.", correct_answer="LIFO"), question_type="dien_khuyet", candidate_index=1)
        self.assertIn("FILL_BLANK_ANSWER_LEAK", {error.code for error in errors})
        errors = validate_question_quality(candidate(question_type="nhieu_lua_chon", question="Khi nào thì bước 5 được thực hiện?"), question_type="nhieu_lua_chon", candidate_index=1)
        self.assertIn("MULTIPLE_RESPONSE_INSTRUCTION_MISSING", {error.code for error in errors})

    def test_question_quality_rejects_external_context_and_answer_leak(self):
        options = {
            "A": "Ngăn xếp hoạt động theo nguyên tắc vào sau ra trước.",
            "B": "Ngăn xếp hoạt động theo nguyên tắc vào trước ra trước.",
            "C": "Ngăn xếp không lưu dữ liệu.",
            "D": "Ngăn xếp chỉ lưu được một phần tử.",
        }
        external = candidate(
            question_type="trac_nghiem",
            question="Theo NGỮ CẢNH, ngăn xếp hoạt động theo nguyên tắc nào?",
            options=options,
            correct_answer="A",
        )
        leaked = candidate(
            question_type="trac_nghiem",
            question=(
                "Câu nào đúng? Ngăn xếp hoạt động theo nguyên tắc vào sau ra trước."
            ),
            options=options,
            correct_answer="A",
        )

        external_codes = {
            error.code
            for error in validate_question_quality(
                external,
                question_type="trac_nghiem",
                candidate_index=1,
            )
        }
        leaked_codes = {
            error.code
            for error in validate_question_quality(
                leaked,
                question_type="trac_nghiem",
                candidate_index=1,
            )
        }

        self.assertIn("CONTEXT_DEPENDENT_QUESTION", external_codes)
        self.assertIn("CORRECT_OPTION_REPEATED_IN_STEM", leaked_codes)

        document_reference = candidate(
            question_type="trac_nghiem",
            question="Đặc trưng nào được nêu trong văn bản? ...?",
            options=options,
            correct_answer="A",
        )
        document_codes = {
            error.code
            for error in validate_question_quality(
                document_reference,
                question_type="trac_nghiem",
                candidate_index=1,
            )
        }
        self.assertIn("CONTEXT_DEPENDENT_QUESTION", document_codes)
        self.assertIn("QUESTION_PLACEHOLDER_ARTIFACT", document_codes)

    def test_multi_select_does_not_repeat_options_in_stem(self):
        item = candidate(
            question_type="nhieu_lua_chon",
            question=(
                "Chọn tất cả đáp án đúng: Đặc điểm nào thuộc giải thuật? "
                "Giải thuật phải dừng sau hữu hạn bước."
            ),
            options={
                "A": "Giải thuật phải dừng sau hữu hạn bước.",
                "B": "Các thao tác phải thực hiện được.",
                "C": "Kết quả luôn phụ thuộc máy tính.",
                "D": "Giải thuật có thể không kết thúc.",
            },
            correct_answer="A, B",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="nhieu_lua_chon", candidate_index=1,
            )
        }

        self.assertIn("OPTION_REPEATED_IN_STEM", codes)

    def test_multi_select_requires_each_correct_option_in_evidence(self):
        item = candidate(
            question_type="nhieu_lua_chon",
            question="Chọn tất cả đáp án đúng: Đặc điểm nào thuộc giải thuật?",
            options={
                "A": "Giải thuật phải dừng sau hữu hạn bước.",
                "B": "Các thao tác phải thực hiện được.",
                "C": "Kết quả luôn phụ thuộc máy tính.",
                "D": "Giải thuật có thể không kết thúc.",
            },
            correct_answer="A, B",
            source_context="Giải thuật phải dừng sau hữu hạn bước.",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="nhieu_lua_chon", candidate_index=1,
            )
        }

        self.assertIn("MULTIPLE_RESPONSE_CORRECT_OPTION_UNGROUNDED", codes)

    def test_multi_select_repairs_quote_from_one_exact_source_block(self):
        from modules.generation.question import _validate_and_format

        context = (
            "Mục lục: [Đặc trưng]\n"
            "Nội dung: Tính kết thúc: Giải thuật dừng sau hữu hạn bước. "
            "Tính xác định: Các máy cho cùng kết quả."
        )
        item = candidate(
            question_type="nhieu_lua_chon",
            question="Chọn tất cả đáp án đúng: Đâu là các đặc trưng được mô tả?",
            options={
                "A": "Giải thuật dừng sau hữu hạn bước.",
                "B": "Các máy cho cùng kết quả.",
                "C": "Giải thuật không cần kết thúc.",
                "D": "Mỗi máy cho một kết quả khác nhau.",
            },
            correct_answer="A, B",
            source_context="Giải thuật dừng sau hữu hạn bước; các máy cho cùng kết quả.",
            source_keywords=[],
            false_mutation=None,
            clo_codes=[],
        )

        kept, errors = _validate_and_format(
            [item], question_type="nhieu_lua_chon", bloom_level="2_hieu",
            context_text=context, allowed_clo_codes=[],
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(
            kept[0].source_context,
            "Giải thuật dừng sau hữu hạn bước. Tính xác định: Các máy cho cùng kết quả.",
        )
        self.assertTrue(kept[0].post_processing["source_context_repaired"])

    def test_multi_select_repairs_narrow_context_reference_stem(self):
        from modules.generation.question import _validate_and_format

        context = (
            "Mục lục: [Đặc trưng]\n"
            "Nội dung: Giải thuật phải dừng sau hữu hạn bước. "
            "Các máy cho cùng kết quả."
        )
        item = candidate(
            question_type="nhieu_lua_chon",
            question=(
                "Chọn tất cả đáp án đúng: Những đặc trưng nào sau đây của "
                "giải thuật được mô tả trong ngữ cảnh?"
            ),
            options={
                "bots": "ignored",
                "A": "Giải thuật phải dừng sau hữu hạn bước.",
                "B": "Các máy cho cùng kết quả.",
                "C": "Giải thuật không cần dừng.",
                "D": "Mỗi máy cho kết quả khác nhau.",
            },
            correct_answer="A,B",
            source_context=(
                "Giải thuật phải dừng sau hữu hạn bước. "
                "Các máy cho cùng kết quả."
            ),
            source_keywords=[],
            false_mutation=None,
            clo_codes=[],
        )
        item["options"].pop("bots")

        kept, errors = _validate_and_format(
            [item], question_type="nhieu_lua_chon", bloom_level="2_hieu",
            context_text=context, allowed_clo_codes=[],
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(
            kept[0].question,
            "Chọn tất cả đáp án đúng: Những nhận định nào sau đây mô tả đúng "
            "các đặc trưng của giải thuật?",
        )
        self.assertEqual(
            kept[0].post_processing["question_repair"],
            "remove_context_reference_from_multiple_response_stem",
        )

    def test_multi_select_does_not_join_evidence_across_source_blocks(self):
        from modules.generation.question import _validate_and_format

        context = (
            "Mục lục: [Một]\nNội dung: Giải thuật dừng sau hữu hạn bước.\n\n---\n\n"
            "Mục lục: [Hai]\nNội dung: Các máy cho cùng kết quả."
        )
        item = candidate(
            question_type="nhieu_lua_chon",
            question="Chọn tất cả đáp án đúng: Đâu là các đặc trưng được mô tả?",
            options={
                "A": "Giải thuật dừng sau hữu hạn bước.",
                "B": "Các máy cho cùng kết quả.",
                "C": "Giải thuật không cần kết thúc.",
                "D": "Mỗi máy cho một kết quả khác nhau.",
            },
            correct_answer="A, B",
            source_context="Giải thuật dừng sau hữu hạn bước. Các máy cho cùng kết quả.",
            source_keywords=[],
            false_mutation=None,
            clo_codes=[],
        )

        kept, errors = _validate_and_format(
            [item], question_type="nhieu_lua_chon", bloom_level="2_hieu",
            context_text=context, allowed_clo_codes=[],
        )

        self.assertEqual(kept, [])
        self.assertIn("SOURCE_CONTEXT_NOT_FOUND", {error.code for error in errors})

    def test_matching_rejects_same_description_in_both_columns(self):
        item = candidate(
            question_type="ghep_cot",
            question="Ghép mỗi mục ở nhóm số với mô tả phù hợp ở nhóm chữ.",
            options={
                "1": "Mục 2: So sánh hai số và chọn số nhỏ nhất",
                "2": "Mục 4: Giảm UCLN một đơn vị",
                "3": "Mục 5: In UCLN và kết thúc",
                "A": "Bước 2: So sánh hai số và chọn số nhỏ nhất",
                "B": "Bước 4: Giảm UCLN một đơn vị",
                "C": "Bước 5: In UCLN và kết thúc",
                "D": "Bước 1: Nhập hai số",
            },
            correct_answer="1-A,2-B,3-C",
        )

        codes = {
            error.code
            for error in validate_question_quality(
                item, question_type="ghep_cot", candidate_index=1,
            )
        }

        self.assertIn("MATCHING_PAIR_DUPLICATED", codes)

    def test_generation_pipeline_rejects_invented_clo_and_wrong_type(self):
        from modules.generation.question import _validate_and_format

        for overrides, code in (({"clo_codes": ["CLO999"]}, "CLO_CODE_NOT_ALLOWED"), ({"question_type": "trac_nghiem"}, "QUESTION_TYPE_MISMATCH")):
            kept, errors = _validate_and_format(
                [candidate(**overrides)], question_type="dung_sai", bloom_level="2_hieu",
                context_text=CONTEXT, allowed_clo_codes=[],
            )
            self.assertEqual(kept, [])
            self.assertIn(code, {error.code for error in errors})

    def test_attached_evidence_uses_same_normalization_as_grounding(self):
        from modules.generation.mongodb import derive_question_evidence

        text = "Mở đầu. " + unicodedata.normalize("NFD", "Ngăn xếp tuân theo LIFO.")
        item = candidate(question_type="trac_nghiem", source_context="ngăn xếp tuân theo LIFO.", source_keywords=[])
        self.assertEqual(validate_source_grounding(item, context_text=text, question_type="trac_nghiem", candidate_index=1), [])
        span = derive_question_evidence(item, [{"chunk_id": "stack", "content": text}])[0]
        self.assertEqual(span["quote"], text[span["char_start"]:span["char_end"]])
        with self.assertRaisesRegex(ValueError, "QUESTION_EVIDENCE_NOT_IN_CHUNK"):
            derive_question_evidence({"source_context": "Ngăn xếp tuân theo LIFO."}, [
                {"chunk_id": "a", "content": "Ngăn xếp"}, {"chunk_id": "b", "content": "tuân theo LIFO."},
            ])

    def test_exact_matching_preserves_vietnamese_diacritics(self):
        self.assertTrue(contains_exact_text("Cây nhị phân", "cây nhị phân"))
        self.assertFalse(contains_exact_text("Cay nhi phan", "cây nhị phân"))
        self.assertFalse(contains_exact_text("Heapsort", "heap"))

    def test_exact_matching_tolerates_ocr_spacing_only(self):
        context = "Giải thuật n ày đạt tính kết thúc trong trường hợp xấu nhất."
        quote = "Giải thuật nà y đạt tính kết thúc trong trường hợp xấu nhất."

        self.assertTrue(contains_exact_text(context, quote))
        self.assertFalse(contains_exact_text(context, "Giải thuật đạt tính hiệu quả."))

    def test_grounding_accepts_exact_keyword_and_controlled_false_mutation(self):
        errors = validate_source_grounding(
            candidate(),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertEqual(errors, [])

    def test_grounding_rejects_keyword_not_in_reference(self):
        errors = validate_source_grounding(
            candidate(source_keywords=["Hàng đợi"]),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("KEYWORD_NOT_IN_EVIDENCE", {error.code for error in errors})

    def test_grounding_rejects_non_string_keyword(self):
        errors = validate_source_grounding(
            candidate(source_keywords=[123]),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("SOURCE_KEYWORDS_INVALID", {error.code for error in errors})

    def test_grounding_sanitizes_optional_mcq_keywords(self):
        item = candidate(
            question="Ngăn xếp (Stack) tuân theo nguyên tắc nào?",
            options={"A": "LIFO", "B": "FIFO", "C": "LILO", "D": "FILO"},
            correct_answer="A",
            question_type="trac_nghiem",
            source_keywords=["Ngăn xếp (Stack)", "không có trong nguồn", 123],
            false_mutation=None,
        )

        errors = validate_source_grounding(
            item,
            context_text=CONTEXT,
            question_type="trac_nghiem",
            candidate_index=1,
        )

        self.assertEqual(errors, [])

    def test_false_mutation_keywords_keep_unchanged_anchors(self):
        item = candidate(source_keywords=["Ngăn xếp (Stack)", "LIFO"])
        self.assertEqual(validate_source_grounding(item, context_text=CONTEXT, question_type="dung_sai", candidate_index=1), [])
        self.assertEqual(item["source_keywords"], ["Ngăn xếp (Stack)"])
        errors = validate_source_grounding(candidate(source_keywords=["LIFO"]), context_text=CONTEXT, question_type="dung_sai", candidate_index=1)
        self.assertIn("SOURCE_KEYWORDS_MISSING", {error.code for error in errors})
        errors = validate_source_grounding(candidate(source_keywords=["Ngăn xếp (Stack)", "LIFO"], false_mutation={"field": "relation", "original": "LIFO", "replacement": "FILO"}), context_text=CONTEXT, question_type="dung_sai", candidate_index=1)
        self.assertIn("MUTATION_REPLACEMENT_NOT_IN_STATEMENT", {error.code for error in errors})
        self.assertIn("KEYWORD_NOT_IN_STATEMENT", {error.code for error in errors})
        self.assertEqual(item["source_keywords"], ["Ngăn xếp (Stack)"])

    def test_false_statement_requires_traceable_mutation(self):
        errors = validate_source_grounding(
            candidate(false_mutation=None),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("FALSE_MUTATION_MISSING", {error.code for error in errors})

    def test_true_statement_must_not_include_false_mutation(self):
        item = candidate(
            question="Ngăn xếp (Stack) tuân theo nguyên tắc LIFO.",
            correct_answer="A",
        )
        errors = validate_source_grounding(
            item,
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("TRUE_STATEMENT_HAS_MUTATION", {error.code for error in errors})

    def test_clarity_rejects_question_and_multiple_propositions(self):
        errors = validate_true_false_clarity(
            candidate(question="Ngăn xếp dùng LIFO; nhưng hàng đợi dùng FIFO?"),
            candidate_index=1,
        )
        codes = {error.code for error in errors}
        self.assertIn("STATEMENT_IS_QUESTION", codes)
        self.assertIn("MULTIPLE_PROPOSITIONS", codes)

    def test_duplicate_filter_detects_exact_and_near_duplicates(self):
        first = GeneratedQuestion(**candidate())
        exact = GeneratedQuestion(**candidate())
        near = GeneratedQuestion(
            **candidate(question="Ngăn xếp (Stack) tuân theo nguyên tắc FIFO trong mọi trường hợp.")
        )
        seen = set()
        kept, stats = filter_duplicate_questions([first, exact, near], seen, limit=3)

        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.exact, 1)
        self.assertEqual(stats.near, 1)
        self.assertIn(question_fingerprint(first.question), seen)

    def test_true_false_prompt_contract_declares_grounding_fields(self):
        prompt_root = BASE_DIR / "prompts"
        structure = (prompt_root / "question_structure" / "dung_sai.txt").read_text(
            encoding="utf-8"
        )
        output_format = (prompt_root / "output_format.txt").read_text(encoding="utf-8")

        self.assertIn("source_keywords", structure)
        self.assertIn("false_mutation", structure)
        self.assertIn("không được kết thúc bằng dấu `?`", structure)
        self.assertIn("tối đa 2 thuật ngữ/cụm từ neo ngắn", structure)
        self.assertIn("source_keywords", output_format)


if __name__ == "__main__":
    unittest.main()
