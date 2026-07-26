# Frontend Teacher Flow - Gap Priority

Cap nhat: 2026-07-26

File nay ghi rieng phan luong giang vien. Kiem duyet/Reviewer co the demo bang cac man hinh da co, nhung khong nen tron vao checklist Teacher neu chi bao cao luong sinh cau hoi.

## 1. Trang thai hien tai

- Generate page co 2 nguon hoc lieu: tai PDF moi hoac chon lai tai lieu da OCR.
- Khi tai PDF moi, frontend goi endpoint nghiep vu `POST /api/v1/documents/upload`; endpoint cu `/api/v1/ocr/upload` chi con la compatibility route.
- Tai lieu failed/cancelled/archived, hoac pipeline OCR/chunk/index failed, da bi an khoi danh sach chon lai de tranh chon nham tai lieu hong.
- Backend hien filter tai lieu/cau hoi theo owner cho Teacher; picker tai lieu va Manage page vi vay chi tra ve du lieu thuoc tai khoan hien tai. Reviewer/Admin van giu quyen xem theo luong kiem duyet/quan tri.
- Man hinh hien tai giu 1 form cau hinh sinh cau hoi va 1 khung xem truoc ben canh; da rollback phan tach thanh 3 section/card lon tren man hinh.
- Teacher co the them/xoa nhieu dong ma tran sinh cau hoi; moi dong gom dang cau hoi, Bloom va so cau.
- Bloom tren UI khong hien so thu tu 1, 2, 3 nua; chi hien ten muc Bloom.
- Chi con 1 o `Yeu cau sinh cau hoi`; noi dung nay duoc gui len backend ca `instruction` va `target_heading`.
- `instruction` duoc dua vao prompt LLM trong block Teacher request.
- `target_heading` giup RAG uu tien truy xuat chunk gan voi noi dung giang vien nhap; neu khong match heading thi backend fallback ve ket qua vector query.
- Co the luu/xoa mau cau hinh sinh cau hoi theo tai khoan qua API `/users/me/generation-presets`; localStorage con la cache/fallback khi API chua dong bo duoc.
- Sau khi sinh, cau hoi AI duoc luu vao DB o trang thai `DRAFT`, co `question_code`, version va `review_status`.
- UI hien thoi gian upload, OCR, chunk/index, sinh cau hoi va tong thoi gian cua lan chay hien tai; voi tai lieu da index san thi hien la tai su dung. Khi enqueue generation, frontend gui them `client_telemetry` de backend persist timing vao `generation_jobs.metrics`.
- Teacher co the sua cau hoi nhap trong preview: noi dung, options, dap an dung va giai thich.
- Teacher co the luu chinh sua, bo/xoa cau hoi nhap, gui tung cau hoi sang kiem duyet hoac gui hang loat cac cau hoi co the submit.
- Manage page da co loc theo trang thai, tai lieu, Bloom/search va co thao tac gui cau hoi `DRAFT`/`NEEDS_REVISION` sang kiem duyet.
- Khi chua dang nhap, header chi hien nhom cong khai; sau login, Teacher moi thay nhom Giang vien, Reviewer moi thay nhom Nguoi duyet, Admin moi thay nhom Admin. Neu truy cap truc tiep route can quyen thi app chuyen sang `/dang-nhap`.
- Sau khi dang nhap, neu tai khoan co quyen voi route vua bam, Login page dieu huong quay lai route do; neu khong thi dieu huong theo role.
- Route guard demo da tach role ro: Teacher dung `/sinh-cau-hoi` va `/quan-ly`; Reviewer dung `/kiem-duyet`; Admin dung `/danh-muc` va `/quan-ly-nguoi-dung`.
- Login page nhan tai khoan demo ngan `admin/admin` va `reviewer/reviewer` qua `/auth/demo-login`; email/password Firebase va Google login van giu nhu cu.
- Route `/ho-so` da duoc bao ve bang role `Admin`/`Teacher`/`Reviewer`.
- Reviewer queue enqueue AI evaluation bang model cau hinh qua `EVALUATION_MODEL_PROVIDER` (mac dinh `deepseek-r1`, co the dung `ollama:<model>`) qua `evaluation_jobs`; neu Ollama/model loi thi luu `ERROR` de reviewer retry hoac duyet thu cong co ly do, khong tinh heuristic la AI pass.
- Co script `backend/scripts/database/seed_demo_review_flow.py` de refresh cau hoi `Q-DEMO-REVIEW-001` ve trang thai `PENDING`/`NOT_STARTED`, giup reviewer co du lieu de chay AI evaluation trong demo.

## 2. P0 da xu ly o muc demo

1. Sinh cau hoi tu tai lieu moi hoac tai lieu da OCR.
2. Cau hinh nhieu dong question plan.
3. Nhap yeu cau sinh cau hoi cua giang vien va dua vao LLM/RAG.
4. Xem truoc cau hoi nhap sau khi sinh.
5. Sua/luu/bo cau hoi nhap.
6. Gui cau hoi nhap sang hang doi kiem duyet.
7. An tai lieu failed khoi picker tai lieu da OCR.
8. Dieu huong truy cap truc tiep route Teacher khi chua dang nhap -> login -> quay lai route Teacher neu co quyen.

## 3. P1 da xu ly o muc demo

- Luu va ap dung mau cau hinh sinh cau hoi theo tai khoan; tu dong migrate mau localStorage len server neu tai khoan chua co mau server-side.
- Xoa mau cau hinh da luu tren server, fallback xoa local khi server chua xac nhan.
- Hien status/code/version cua cau hoi nhap.
- Loc cau hoi trong Manage theo trang thai, tai lieu, Bloom va keyword.
- Gui hang loat cau hoi nhap sang kiem duyet.
- Backend smoke E2E `backend/scripts/run_e2e_ocr_questions.py` da chay qua OCR -> chunk/index -> RAG -> Qwen -> luu cau hoi V2 o trang thai `DRAFT`.
- Backend da hardening output format va retry 1 lan khi LLM tra thieu/sai format cau hoi, giam rui ro MCQ bi thieu 4 lua chon.

## 4. P2 da xu ly hoac tam chap nhan

- Placeholder vi du trong o yeu cau da lam mo hon de tranh nguoi dung tuong la noi dung that.
- Layout giu gon trong mot form, khong tach thanh 3 hop lon tren man hinh.
- Preset da co API/DB theo tai khoan; localStorage chi con dung lam cache va fallback offline/auth loi.
- Generate page da hien thoi gian xu ly cua lan chay hien tai va backend persist timing client/server buoc dau vao `generation_jobs.metrics`.
- Header guest chi hien nhom cong khai; cac module theo quyen chi hien sau login, permission that van nam o route guard/backend.
- Ownership Teacher da siết o backend cho tai lieu/cau hoi; frontend chua can them UI rieng vi list API da tra ve theo quyen.
- Reviewer queue da co du lieu seed demo rieng bang `python scripts/database/seed_demo_review_flow.py`; day la phan Human-in-the-loop tach khoi checklist Teacher.
- Upload endpoint da nhan san `subject_id`/`chapter_id` neu UI gui kem, nhung Generate page hien chua co picker hoc phan/chuong luc upload nen van dung metadata mac dinh.

## 5. Con thieu / khong nen claim qua muc

- Telemetry timing da persist buoc dau theo tung generation job trong `generation_jobs.metrics`; chua co dashboard thong ke nhieu lan chay hoac collection telemetry rieng.
- Chua co E2E UI tu dong cho toan bo luong Teacher voi tai khoan Firebase va PDF mau; hien moi co backend smoke E2E.
- Chua smoke test thu cong lai toan bo chuoi voi browser that sau thay doi login/menu: guest truy cap truc tiep `/sinh-cau-hoi` -> login Google -> quay lai `/sinh-cau-hoi` -> generate.
- Reviewer flow khong nen noi la do luong Teacher hoan thanh; do la phan Human-in-the-loop rieng.
- Prompt template he thong khong sua truc tiep trong Generate page; Teacher chi nhap request cho tung lan sinh.
- Can benchmark them chat luong MCQ voi nhieu PDF/model that; hien moi hardening format o muc demo.
- Chua co UI chia se/chuyen owner tai lieu/cau hoi giua nhieu giang vien; neu can dung chung hoc lieu thi can thiet ke policy rieng.
- Chua co UI chon hoc phan/chuong khi upload PDF moi tren Generate page; API da co form field `subject_id`/`chapter_id` nhung frontend chua truyen.

## 6. Nen lam tiep neu muon chac demo

1. Smoke test bang UI voi 1 PDF that: upload/OCR -> generate -> sua -> luu -> gui duyet.
2. Smoke test chon lai tai lieu da OCR, dam bao tai lieu failed khong hien trong picker.
3. Kiem tra Manage page sau khi gui duyet: cau hoi chuyen tu `DRAFT` sang `PENDING`.
4. Smoke test preset voi tai khoan Firebase that: luu mau tren may A -> dang nhap may/trinh duyet B -> thay mau da dong bo.
5. Neu can tai khoan Reviewer demo, dung `reviewer/reviewer` hoac seed lai bang `python scripts/database/seed_demo_users.py`; neu can cau hoi cho Reviewer thi chay `python scripts/database/seed_demo_review_flow.py`.
6. Neu dung Google/email that thi sync user truoc roi chay `python scripts/database/set_user_role.py --email <email> --role Reviewer`.
7. Smoke test route guard: guest chi thay menu cong khai, truy cap truc tiep route can quyen thi ve login; sau login menu mo cac nhom theo role that.

## 7. Cau noi khi bao cao

- "Luong Teacher da ho tro tai su dung tai lieu OCR, tao ma tran cau hoi nhieu dong, nhap yeu cau sinh cau hoi va xem/sua ban nhap truoc khi gui kiem duyet."
- "Cau hoi AI khong di thang vao ngan hang da duyet; mac dinh la `DRAFT` de giang vien ra soat."
- "Preset cau hinh da dong bo theo tai khoan qua DB; localStorage chi la cache/fallback de demo khong bi chan khi API/auth tam loi."
- "Trang chu/gioi thieu co the xem cong khai; cac module theo quyen chi hien sau login va van duoc route guard/backend kiem tra truoc khi dung."

## 8. Handoff nhanh cho chat tiep theo

- Branch hien tai: `nckh/v2-demo-hardening`.
- Build frontend gan nhat: `npm run build` pass; con warning Vite ve chunk JS lon hon 500KB.
- Browser-test cu truoc khi doi header: guest header tren `http://127.0.0.1:5174/trang-chu` hien 9 muc menu, khong de nut login, bam `Sinh Cau Hoi` chuyen ve `/dang-nhap`. Header hien da doi sang chi hien nhom cong khai khi chua login.
- Dev server test co the dang chay o `http://127.0.0.1:5174/trang-chu`.
- Chua stage/commit thay doi.
- Viec nen lam tiep dau tien: smoke test login Google that va luong Teacher end-to-end tren browser cua nguoi dung.
