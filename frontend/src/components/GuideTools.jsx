import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { BLOOM_LEVELS, DIFFICULTIES, QUESTION_TYPES, allowedBloomLevels, normalizeBloomForQuestionType } from '../constants/generationEnums';

const initialConfig = { type: 'mcq', bloom: 'understand', difficulty: 'trung_binh', count: '3', content: 'code' };
const contentLabels = { auto: 'Tự nhận diện', code: 'Có mã nguồn', general: 'Lý thuyết' };
const issues = [
  { id: 'subject', title: 'Không thấy học phần', steps: ['Mở Quản lý học phần và kiểm tra học phần đã được tạo, còn hoạt động.', 'Quay lại Sinh câu hỏi và tải lại trang khi không có tác vụ đang chạy.', 'Nếu tài khoản không có quyền quản lý học phần, liên hệ quản trị viên.'], link: '/quan-ly-hoc-phan', action: 'Quản lý học phần' },
  { id: 'document', title: 'Không thấy tài liệu cũ', steps: ['Chọn Chọn tài liệu đã xử lý, rồi bấm Tải lại.', 'Kiểm tra tài liệu đã xử lý thành công và tài khoản có quyền truy cập.', 'Nếu chưa có tài liệu đủ điều kiện, dùng Tải tài liệu mới và chờ xử lý hoàn tất.'], link: '/sinh-cau-hoi', action: 'Sinh câu hỏi' },
  { id: 'ocr', title: 'Lỗi xử lý tài liệu / OCR', steps: ['Kiểm tra file mở được, không có mật khẩu và thuộc PDF, DOC/DOCX, Markdown hoặc TXT.', 'Với bản scan, kiểm tra chữ rõ nét, trang đúng chiều và đủ nội dung.', 'Chuẩn bị lại file rồi thử xử lý lại. Nếu lỗi lặp lại, ghi thông báo lỗi và tên tài liệu để được hỗ trợ.'], link: '/sinh-cau-hoi', action: 'Sinh câu hỏi' },
  { id: 'generate', title: 'Không sinh được câu hỏi', steps: ['Kiểm tra tài liệu đã sẵn sàng, tổng số câu từ 1 đến 7 và không có tác vụ đang chạy.', 'Chọn phạm vi có đủ dữ kiện trong tài liệu; thử giảm số câu hoặc điều chỉnh ma trận.', 'Kiểm tra mô hình đã chọn và đọc thông báo lỗi. Thử lại khi trang cho phép; ghi tên mô hình và lỗi nếu vẫn thất bại.'], link: '/sinh-cau-hoi', action: 'Sinh câu hỏi' },
  { id: 'code', title: 'Câu hỏi thiếu mã nguồn', steps: ['Chưa gửi duyệt. Đối chiếu dẫn chứng để xác định đoạn mã và dữ kiện cần thiết.', 'Dùng Sửa để bổ sung đoạn mã, rồi kiểm tra lại đáp án và giải thích.', 'Nếu không xác minh được, dùng Bỏ câu. Khi tạo lại, chọn Có mã nguồn và nguồn có đoạn mã đầy đủ.'], link: '/sinh-cau-hoi', action: 'Sinh câu hỏi' },
  { id: 'revision', title: 'Câu hỏi cần sửa sau duyệt', steps: ['Mở Quản lý câu hỏi, tìm câu có trạng thái Cần sửa và đọc góp ý.', 'Sửa đúng dữ kiện, đáp án hoặc tiêu chí được phản hồi; đối chiếu lại tài liệu.', 'Gửi duyệt lại sau khi rà soát và theo dõi phản hồi mới.'], link: '/quan-ly', action: 'Quản lý câu hỏi' },
];

export function GuideConfigSandbox() {
  const [config, setConfig] = useState(initialConfig);
  const allowed = allowedBloomLevels(config.type);
  const count = Number(config.count);
  const countValid = config.count !== '' && Number.isInteger(count) && count >= 1 && count <= 7;
  const change = (key, value) => setConfig((previous) => ({ ...previous, [key]: value }));
  const changeType = (type) => setConfig((previous) => ({ ...previous, type, bloom: normalizeBloomForQuestionType(type, previous.bloom) }));
  const selectedType = QUESTION_TYPES.find((type) => type.id === config.type);
  const selectedBloom = BLOOM_LEVELS.find((level) => level.id === config.bloom);
  return (
    <section className="guide-interactive" id="guide-try" aria-labelledby="guide-try-title">
      <div className="container">
        <div className="section-header"><h2 className="section-title" id="guide-try-title">Thử cấu hình sinh câu hỏi</h2><p className="section-desc">Thử cấu hình — không tạo câu hỏi thật. Các lựa chọn chỉ dùng để học cách thiết lập.</p></div>
        <div className="guide-sandbox">
          <div className="guide-sandbox-fields">
            <label htmlFor="guide-question-type">Dạng câu hỏi<select id="guide-question-type" value={config.type} onChange={(event) => changeType(event.target.value)}>{QUESTION_TYPES.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}</select></label>
            <label htmlFor="guide-bloom">Mức nhận thức Bloom<select id="guide-bloom" value={config.bloom} onChange={(event) => change('bloom', event.target.value)} aria-describedby="guide-bloom-help">{BLOOM_LEVELS.map((level) => <option key={level.id} value={level.id} disabled={!allowed.some((item) => item.id === level.id)}>{level.label}{allowed.some((item) => item.id === level.id) ? '' : ' · Không phù hợp'}</option>)}</select></label>
            <p id="guide-bloom-help" className="guide-field-help">{selectedType.label} hỗ trợ {allowed.map((level) => level.label.replace(/^\d\. /, '')).join(', ')}. Khi đổi dạng câu hỏi, mức không phù hợp được chuyển sang mức hợp lệ.</p>
            <label htmlFor="guide-difficulty">Độ khó<select id="guide-difficulty" value={config.difficulty} onChange={(event) => change('difficulty', event.target.value)}>{DIFFICULTIES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            <label htmlFor="guide-count">Số câu<input id="guide-count" type="number" min="1" max="7" step="1" value={config.count} onChange={(event) => change('count', event.target.value)} aria-invalid={!countValid} aria-describedby="guide-count-help" /></label>
            <p id="guide-count-help" className={`guide-field-help ${countValid ? '' : 'guide-field-error'}`}>{countValid ? 'Tổng số câu mỗi lượt: từ 1 đến 7.' : 'Nhập số nguyên từ 1 đến 7 để có cấu hình hợp lệ.'}</p>
            <label htmlFor="guide-content">Nội dung<select id="guide-content" value={config.content} onChange={(event) => change('content', event.target.value)}>{Object.entries(contentLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          </div>
          <aside className="guide-config-result" aria-label="Nhận xét cấu hình">
            <span className="guide-example-label">Cấu hình của bạn</span>
            <div aria-live="polite" aria-atomic="true"><h3>{selectedType.label}</h3><p><strong>{selectedBloom.label}</strong> · {DIFFICULTIES.find((item) => item.id === config.difficulty).label}</p><p>{countValid ? `${count} câu` : 'Số câu chưa hợp lệ'} · {contentLabels[config.content]}</p><p className="guide-config-tip">{config.content === 'code' ? 'Chuẩn bị nguồn có đoạn mã đầy đủ. Khi rà soát, đề phải cung cấp đoạn mã và giá trị ban đầu cần thiết.' : config.content === 'general' ? 'Dùng nguồn có khái niệm, định nghĩa hoặc lập luận rõ ràng; kiểm tra câu hỏi có đủ dữ kiện để trả lời.' : 'Hệ thống xác định nội dung theo nguồn. Vẫn cần kiểm tra đề, đáp án và dẫn chứng sau khi sinh.'}</p></div>
            <div className="guide-tool-actions"><button type="button" className="btn btn--outline" onClick={() => setConfig(initialConfig)}>Đặt lại cấu hình</button><Link to="/sinh-cau-hoi" className="btn btn--primary">Đến Sinh câu hỏi</Link></div>
            <p className="guide-field-help">Cấu hình thử không được lưu hoặc chuyển sang trang Sinh câu hỏi.</p>
          </aside>
        </div>
      </div>
    </section>
  );
}

export function GuideTroubleshooter() {
  const [selectedId, setSelectedId] = useState(issues[0].id);
  const [checked, setChecked] = useState([]);
  const selected = issues.find((issue) => issue.id === selectedId);
  const selectIssue = (id) => { setSelectedId(id); setChecked([]); };
  const toggle = (index) => setChecked((previous) => previous.includes(index) ? previous.filter((item) => item !== index) : [...previous, index]);
  return (
    <section className="guide-interactive guide-troubleshooter" id="guide-help" aria-labelledby="guide-help-title">
      <div className="container">
        <div className="section-header"><h2 className="section-title" id="guide-help-title">Bạn đang gặp vấn đề gì?</h2><p className="section-desc">Chọn tình huống và đánh dấu từng bước đã kiểm tra. Công cụ không tự kiểm tra dữ liệu tài khoản.</p></div>
        <div className="guide-help-layout">
          <div className="guide-issue-options" role="group" aria-label="Chọn vấn đề">{issues.map((issue) => <button type="button" key={issue.id} aria-pressed={issue.id === selectedId} aria-controls="guide-help-result" onClick={() => selectIssue(issue.id)}>{issue.title}</button>)}</div>
          <div className="guide-help-result" id="guide-help-result">
            <h3>{selected.title}</h3>
            <p className="guide-check-progress" role="status">Đã kiểm tra {checked.length}/{selected.steps.length} bước{checked.length === selected.steps.length ? ' · Nếu vẫn lỗi, ghi lại thông báo để liên hệ hỗ trợ.' : ''}</p>
            <ol className="guide-checklist">{selected.steps.map((step, index) => <li key={`${selected.id}-${index}`}><label><input type="checkbox" checked={checked.includes(index)} onChange={() => toggle(index)} /><span>{step}</span></label></li>)}</ol>
            <div className="guide-tool-actions"><button type="button" className="btn btn--outline" onClick={() => setChecked([])}>Bỏ đánh dấu</button><Link to={selected.link} className="btn btn--primary">Mở {selected.action}</Link></div>
            <p className="guide-field-help">Đánh dấu chỉ là ghi nhận của bạn, không xác nhận lỗi đã được sửa. Tiến độ không lưu khi rời trang.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
