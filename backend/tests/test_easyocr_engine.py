from modules.ocr.easyocr_engine import _line_text


def test_line_text_restores_reading_order() -> None:
    detections = [
        ([[70, 10], [120, 10], [120, 30], [70, 30]], "giới", 0.9),
        ([[10, 50], [80, 50], [80, 70], [10, 70]], "Dòng hai", 0.9),
        ([[10, 10], [60, 10], [60, 30], [10, 30]], "Xin", 0.9),
    ]

    assert _line_text(detections) == "Xin giới\nDòng hai"
