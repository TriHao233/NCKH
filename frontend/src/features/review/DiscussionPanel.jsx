import { useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faComments, faPaperPlane } from '@fortawesome/free-solid-svg-icons';
import {
  addQuestionComment,
  deleteQuestionComment,
  listQuestionComments,
  updateQuestionComment,
} from '../../api/questions';
import { EmptyState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import { formatDateTime, refId } from './reviewModel';
import { userName } from './reviewData';

const ROLE_LABEL = {
  Admin: 'Quản trị viên',
  Teacher: 'Giảng viên',
  Reviewer: 'Người duyệt',
};

/** Trao đổi giữa người duyệt và giảng viên trên từng câu hỏi (có nhắc tên để gửi thông báo). */
function DiscussionPanel({ questionId, user, people, confirm, onCountChange }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [body, setBody] = useState('');
  const [mentions, setMentions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState('');
  const [editingBody, setEditingBody] = useState('');

  const reload = async () => {
    const result = await listQuestionComments(questionId);
    const items = result.items || [];
    setComments(items);
    onCountChange?.(items.length);
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setBody('');
    setMentions([]);
    setEditingId('');
    listQuestionComments(questionId)
      .then((result) => {
        if (!active) return;
        const items = result.items || [];
        setComments(items);
        onCountChange?.(items.length);
      })
      .catch((loadError) => active && setError(loadError.message || 'Không tải được trao đổi.'))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionId]);

  const peopleById = useMemo(() => new Map(people.map((person) => [refId(person), person])), [people]);

  const submit = async (event) => {
    event.preventDefault();
    const text = body.trim();
    if (!text) {
      setError('Nhập nội dung trao đổi.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await addQuestionComment(questionId, { body: text, mention_user_ids: mentions });
      setBody('');
      setMentions([]);
      await reload();
    } catch (submitError) {
      setError(submitError.message || 'Không gửi được bình luận.');
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (comment) => {
    const text = editingBody.trim();
    if (!text) return;
    setBusy(true);
    setError('');
    try {
      await updateQuestionComment(questionId, refId(comment), { body: text });
      setEditingId('');
      await reload();
    } catch (editError) {
      setError(editError.message || 'Không sửa được bình luận.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (comment) => {
    const accepted = await confirm({
      title: 'Xoá bình luận',
      description: 'Bình luận sẽ bị xoá khỏi trao đổi của câu hỏi này.',
      confirmLabel: 'Xoá',
      tone: 'danger',
    });
    if (!accepted) return;
    setBusy(true);
    setError('');
    try {
      await deleteQuestionComment(questionId, refId(comment));
      await reload();
    } catch (removeError) {
      setError(removeError.message || 'Không xoá được bình luận.');
    } finally {
      setBusy(false);
    }
  };

  const toggleMention = (id) => {
    setMentions((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };

  if (loading) return <SkeletonRows rows={2} lines={2} />;

  return (
    <div>
      {comments.length === 0 ? (
        <EmptyState compact icon={faComments} title="Chưa có trao đổi" description="Đặt câu hỏi cho giảng viên hoặc ghi chú cho người duyệt khác tại đây." />
      ) : (
        <div className="rv-thread">
          {comments.map((comment) => {
            const id = refId(comment);
            const mine = refId(comment.author_user_id) === String(user?.id || '');
            const author = peopleById.get(refId(comment.author_user_id));
            const canEdit = mine || user?.role === 'Admin';
            return (
              <article className={`rv-comment ${mine ? 'rv-comment--mine' : ''}`} key={id}>
                <header>
                  <b>{mine ? 'Bạn' : userName(author, ROLE_LABEL[comment.author_role] || 'Người dùng')}</b>
                  <span>{formatDateTime(comment.created_at)}{comment.edited_at ? ', đã sửa' : ''}</span>
                </header>
                {editingId === id ? (
                  <>
                    <textarea
                      className="ws-textarea"
                      value={editingBody}
                      maxLength={2000}
                      onChange={(event) => setEditingBody(event.target.value)}
                      aria-label="Sửa bình luận"
                    />
                    <div className="rv-comment__actions">
                      <button type="button" className="btn btn--primary btn--sm" disabled={busy || !editingBody.trim()} onClick={() => saveEdit(comment)}>Lưu</button>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditingId('')}>Huỷ</button>
                    </div>
                  </>
                ) : (
                  <>
                    <p>{comment.body}</p>
                    {canEdit && (
                      <div className="rv-comment__actions">
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => {
                            setEditingId(id);
                            setEditingBody(comment.body || '');
                          }}
                        >
                          Sửa
                        </button>
                        <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={() => remove(comment)}>Xoá</button>
                      </div>
                    )}
                  </>
                )}
              </article>
            );
          })}
        </div>
      )}

      <form onSubmit={submit} className="ws-field" style={{ gap: 10 }}>
        <label className="ws-field">
          <span>Gửi trao đổi</span>
          <textarea
            className="ws-textarea"
            value={body}
            maxLength={2000}
            onChange={(event) => setBody(event.target.value)}
            placeholder="Ví dụ: Phương án C lấy từ trang nào của tài liệu?"
          />
        </label>
        {people.length > 0 && (
          <div className="ws-field">
            <span className="ws-label">Nhắc tên để gửi thông báo</span>
            <div className="rv-mention-list">
              {people.filter((person) => refId(person) !== String(user?.id || '')).slice(0, 12).map((person) => (
                <button
                  type="button"
                  key={refId(person)}
                  className="rv-mention"
                  aria-pressed={mentions.includes(refId(person))}
                  onClick={() => toggleMention(refId(person))}
                >
                  {userName(person)}
                </button>
              ))}
            </div>
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div>
          <button type="submit" className="btn btn--primary" disabled={busy || !body.trim()}>
            <FontAwesomeIcon icon={faPaperPlane} />
            {busy ? 'Đang gửi...' : 'Gửi'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DiscussionPanel;
