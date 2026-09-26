import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from modules.dictionary.dictionary import _parse_keywords, run_dictionary_auto_learning


class KeywordOutputTests(unittest.IsolatedAsyncioTestCase):
    def test_parser_accepts_schema_and_legacy_array(self):
        self.assertEqual(_parse_keywords('{"keywords": [" con trỏ ", "", 7]}'), ["con trỏ"])
        self.assertEqual(_parse_keywords('["mảng động"]'), ["mảng động"])
        self.assertIsNone(_parse_keywords('{"explanation": "không có danh sách"}'))

    async def test_auto_learning_saves_only_valid_keyword_list(self):
        database = MagicMock()
        database.document_pages.find.return_value.sort.return_value.limit.return_value = [
            {"cleaned_text": "Giải thuật và cấu trúc dữ liệu. " * 12}
        ]
        provider = MagicMock()
        provider.generate_chat = AsyncMock(return_value='{"keywords": ["con trỏ", "mảng động"]}')
        with (
            patch("modules.dictionary.dictionary.get_rag_db", return_value=database),
            patch("modules.generation.llm.factory.get_llm_service", return_value=provider),
            patch("modules.dictionary.dictionary.add_pending_keywords") as save,
        ):
            await run_dictionary_auto_learning("507f1f77bcf86cd799439011")
            save.assert_called_once_with(
                course_id="it_fundamentals", keywords=["con trỏ", "mảng động"]
            )
            self.assertEqual(provider.generate_chat.call_args.kwargs["output_schema"]["required"], ["keywords"])

            provider.generate_chat.return_value = '{"explanation": "không có danh sách"}'
            save.reset_mock()
            await run_dictionary_auto_learning("507f1f77bcf86cd799439011")
            save.assert_not_called()
