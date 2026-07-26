# Prompt va LLM - trang thai hien tai

Cap nhat: 2026-07-26

## Ket luan nhanh

Prompt co duoc dua vao LLM.

Hien tai backend mac dinh dung prompt file trong `backend/prompts`:

```env
PROMPT_SOURCE=file
```

Neu muon dung prompt template trong MongoDB, set:

```env
PROMPT_SOURCE=db
```

Khi `PROMPT_SOURCE=db`, backend moi uu tien template active trong collection `prompt_templates`. Neu DB khong co template active, backend fallback ve file local.

## Giang vien nhap prompt o dau?

Tren Generate page, giang vien nhap vao o:

```text
Yeu cau sinh cau hoi
```

Frontend gui cung mot noi dung nay len backend theo 2 truong:

```json
{
  "instruction": "...",
  "target_heading": "..."
}
```

- `instruction`: duoc ghep vao prompt LLM trong block `TEACHER REQUEST`.
- `target_heading`: duoc dung truoc do de RAG uu tien tim chunk gan voi noi dung/muc/chapter giang vien muon hoi.
  Neu noi dung giang vien nhap khong trung heading/muc luc nao, backend fallback ve ket qua vector query thay vi fail.

Vi vay, o nay khong phai prompt system day du. No la yeu cau bo sung cua giang vien cho tung lan sinh cau hoi.

## Luong generate hien tai

0. Neu la tai lieu moi, frontend goi `POST /api/v1/documents/upload`, poll OCR, goi chunk/index; endpoint cu `/api/v1/ocr/upload` chi con la compatibility route.
1. Frontend goi `POST /api/v1/generate/questions`.
2. Payload chinh gom:
   - `document_id`
   - `collection_name`
   - `question_plan`
   - `instruction`
   - `target_heading`
3. Backend lay context tu RAG bang `get_context_snapshot(...)`, co dung `target_heading` neu co.
4. Backend goi `PromptBuilder.build(...)` de ghep:
   - system prompt
   - bloom prompt
   - question type prompt
   - teacher instruction
   - context tu RAG
   - output format
5. Backend goi LLM bang `llm.generate_text(full_prompt)`.
6. Backend luu prompt da render vao `generation_runs.rendered_prompt`.
7. Backend persist timing cua job sinh vao `generation_jobs.metrics`; neu frontend gui `client_telemetry` thi metrics co ca timing upload/OCR/chunk da do o UI.

Cap nhat kiem chung:

- Script `backend/scripts/run_e2e_ocr_questions.py` da chay duoc luong smoke OCR -> chunk/index -> RAG -> Qwen -> luu cau hoi V2.
- Smoke E2E mac dinh dung dang `dung_sai` de kiem tra pipeline on dinh.
- Da hardening `output_format.txt` va them retry 1 lan khi LLM tra thieu/sai format cau hoi. Co the test rieng MCQ bang `E2E_QUESTION_TYPE=trac_nghiem E2E_NUM_QUESTIONS=1 python scripts/run_e2e_ocr_questions.py`.
- MCQ 4 lua chon van nen benchmark them voi PDF that/model that truoc khi claim chat luong production.

Code lien quan:

- `backend/modules/generation/prompt_builder.py`
- `backend/modules/generation/question.py`
- `backend/modules/generation/schemas.py`
- `backend/modules/rag/search.py`
- `frontend/src/pages/GeneratePage.jsx`

## Preset co lien quan prompt khong?

Co, nhung chi o muc request cua giang vien.

Preset hien tai luu chinh theo tai khoan qua API `/users/me/generation-presets`, localStorage chi con la cache/fallback:

- ma tran cau hoi
- yeu cau sinh cau hoi

Preset khong luu system prompt, prompt Bloom, prompt question type hay output format.

Khi server chua co preset, frontend co co che migrate preset cu trong localStorage len DB. Neu API/auth tam loi, preset van co the fallback ve localStorage de demo khong bi chan.

## Vi sao cau hoi van co the khac ky vong?

1. `target_heading` chi giup truy xuat context, khong dam bao RAG lay dung toan bo chuong.
2. LLM chi thay cac chunk nam trong block `CONTEXT`, khong doc toan bo PDF.
3. `instruction` bi gioi han boi context va schema output.
4. Neu dang chay `PROMPT_SOURCE=db`, DB template active co the khac file local.
5. Model co tinh khong deterministic, nhat la khi chay local provider.

## Cach kiem tra prompt that su gui vao LLM

Xem MongoDB collection `generation_runs`:

- `rendered_prompt`: prompt da gui vao LLM.
- `raw_model_response`: output tho cua model.
- `retrieval_results`: cac chunk/context da lay tu RAG neu co luu.

Kiem tra cac marker:

- `TEACHER REQUEST:`
- `CONTEXT:`
- `TASK:`
- `OUTPUT FORMAT:`

Neu `TEACHER REQUEST` co noi dung giang vien nhap, prompt da nhan request do.

## Cach sua prompt

### Cach A - Sua file prompt local

Dung khi giu mac dinh:

```env
PROMPT_SOURCE=file
```

Sua file trong `backend/prompts`, restart backend neu process dang chay cache code/module.

### Cach B - Sua prompt template trong DB

Dung khi muon quan ly prompt runtime:

```env
PROMPT_SOURCE=db
```

Sau do cap nhat collection `prompt_templates` qua API catalog/Admin hoac MongoDB.

### Cach C - Sua request rieng cua giang vien

Dung o Generate page, o `Yeu cau sinh cau hoi`.

Vi du:

```text
Tap trung vao cay nhi phan tim kiem, tao cau hoi van dung, tranh cau hoi dinh nghia.
```

Noi dung nay se vao `instruction` va `target_heading`, nhung khong thay the system prompt.

## Con thieu lien quan prompt/LLM

- Chua co E2E UI tu dong de chung minh prompt giang vien di tu form -> API -> `generation_runs.rendered_prompt` voi auth that.
- Chua benchmark chat luong cau hoi tren nhieu PDF/model that; hien moi hardening output format va retry 1 lan de on dinh demo.
- Prompt/evaluator parser cho AI evaluation can them test chat luong rieng truoc khi claim production.
- Workflow prompt template trong DB moi o muc Admin/catalog demo; chua co promote/rollback/review version chat che.
