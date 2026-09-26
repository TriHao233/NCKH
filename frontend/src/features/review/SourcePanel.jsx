import { useEffect, useState } from 'react';
import { faFileCircleQuestion } from '@fortawesome/free-solid-svg-icons';
import { fetchQuestionSourcePdf } from '../../api/questions';
import { EmptyState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import { firstSourcePage, pageRangeLabel } from './reviewModel';

/**
 * Tài liệu nguồn của câu hỏi: đoạn trích dẫn, PDF nhảy đúng trang (nếu có) và văn bản trang.
 * PDF chỉ tải khi tab được mở lần đầu để không làm chậm phiên duyệt.
 */
function SourcePanel({ questionId, viewer, loading, error, active }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [activePage, setActivePage] = useState(1);
  const [pdf, setPdf] = useState({ status: 'idle', url: '', error: '' });

  const items = viewer?.items || [];
  const documentInfo = viewer?.document || {};
  const pdfAvailable = Boolean(documentInfo.pdf_available);

  useEffect(() => {
    setActiveIndex(0);
    setActivePage(firstSourcePage(viewer?.items?.[0]));
    setPdf({ status: 'idle', url: '', error: '' });
  }, [questionId, viewer]);

  useEffect(() => {
    if (!active || !pdfAvailable || pdf.status !== 'idle') return undefined;
    let cancelled = false;
    setPdf({ status: 'loading', url: '', error: '' });
    fetchQuestionSourcePdf(questionId)
      .then((result) => {
        if (cancelled) {
          URL.revokeObjectURL(result.url);
          return;
        }
        setPdf({ status: 'ready', url: result.url, error: '' });
      })
      .catch((pdfError) => {
        if (!cancelled) setPdf({ status: 'error', url: '', error: pdfError.message || 'Không mở được PDF nguồn.' });
      });
    return () => {
      cancelled = true;
    };
  }, [active, pdfAvailable, pdf.status, questionId]);

  useEffect(() => () => {
    if (pdf.url) URL.revokeObjectURL(pdf.url);
  }, [pdf.url]);

  if (loading) return <SkeletonRows rows={3} lines={3} />;
  if (error) return <Notice tone="error">{error}</Notice>;

  const warnings = viewer?.warnings || [];

  if (items.length === 0) {
    return (
      <>
        {warnings.map((warning) => <Notice key={warning} tone="warn">{warning}</Notice>)}
        <EmptyState
          compact
          icon={faFileCircleQuestion}
          title="Câu hỏi không có nguồn tham chiếu"
          description="Không thể đối chiếu với tài liệu. Cân nhắc yêu cầu giảng viên bổ sung nguồn trước khi duyệt."
        />
      </>
    );
  }

  const source = items[activeIndex] || items[0];
  const pages = source?.pages || [];
  const pageRecord = pages.find((item) => item.page_number === activePage) || pages[0] || null;
  const currentPage = pageRecord?.page_number || activePage || 1;
  const excerpt = source?.context_excerpt || '';
  const pageText = pageRecord?.text || source?.chunk_text || '';

  return (
    <div>
      <div className="ws-meta" style={{ marginBottom: 12 }}>
        <span>Tài liệu <b>{documentInfo.title || documentInfo.original_filename || 'Không rõ tên'}</b></span>
      </div>
      {warnings.map((warning) => (
        <div key={warning} style={{ marginBottom: 10 }}><Notice tone="warn">{warning}</Notice></div>
      ))}

      <div className="rv-source-list" role="tablist" aria-label="Đoạn nguồn">
        {items.map((item, index) => (
          <button
            key={item.chunk_id || index}
            type="button"
            role="tab"
            aria-selected={index === activeIndex}
            className={`rv-source-chip ${index === activeIndex ? 'rv-source-chip--active' : ''}`}
            onClick={() => {
              setActiveIndex(index);
              setActivePage(firstSourcePage(item));
            }}
          >
            <span>Nguồn {item.citation_order || index + 1}</span>
            <b>{pageRangeLabel(item.page_range)}</b>
            {item.is_current_chunk_set === false && <em>Bản cắt cũ</em>}
          </button>
        ))}
      </div>

      {(source?.warnings || []).map((warning) => (
        <div key={warning} style={{ marginBottom: 10 }}><Notice tone="warn">{warning}</Notice></div>
      ))}

      {pages.length > 1 && (
        <div className="rv-page-tabs" aria-label="Trang">
          {pages.map((item) => (
            <button
              key={item.page_number}
              type="button"
              aria-pressed={item.page_number === currentPage}
              onClick={() => setActivePage(item.page_number)}
            >
              Trang {item.page_number}
            </button>
          ))}
        </div>
      )}

      {pdfAvailable && (
        <div className={`rv-pdf ${pdf.url ? '' : 'rv-pdf--empty'}`}>
          {pdf.status === 'loading' && <SkeletonRows rows={2} lines={2} />}
          {pdf.status === 'error' && <Notice tone="warn">{`${pdf.error} Đối chiếu bằng đoạn văn bản bên dưới.`}</Notice>}
          {pdf.url && (
            <iframe
              key={`${pdf.url}-${currentPage}`}
              src={`${pdf.url}#page=${currentPage}`}
              title={`PDF nguồn ${documentInfo.original_filename || ''}`}
            />
          )}
        </div>
      )}

      <div className="rv-source-text">
        {excerpt && <p><mark>{excerpt}</mark></p>}
        {pageText.trim() !== excerpt.trim() && <p>{pageText || 'Chưa trích xuất được nội dung trang này.'}</p>}
      </div>
    </div>
  );
}

export default SourcePanel;
