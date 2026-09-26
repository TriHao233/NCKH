import { useEffect, useMemo, useState } from 'react';
import { claimQuestionReview, listQuestions } from '../../api/questions';
import { listSubjects } from '../../api/catalog';
import { listReviewerOptions, listTeacherOptions } from '../../api/users';
import {
  canClaim,
  isAssignedToUser,
  isBlockedFromSecondary,
  isLockExpired,
  refId,
} from './reviewModel';

// Danh mục ít thay đổi: giữ trong bộ nhớ 5 phút để chuyển qua lại giữa hàng đợi và phiên duyệt không phải tải lại.
const LOOKUP_TTL_MS = 5 * 60 * 1000;
let lookupCache = null;
let lookupCachedAt = 0;
let lookupPromise = null;

function freshCache() {
  return lookupCache && Date.now() - lookupCachedAt < LOOKUP_TTL_MS ? lookupCache : null;
}

async function loadLookups() {
  const [subjects, teachers, reviewers] = await Promise.allSettled([
    listSubjects(),
    listTeacherOptions(),
    listReviewerOptions(),
  ]);
  return {
    subjects: subjects.status === 'fulfilled' ? (subjects.value || []) : [],
    teachers: teachers.status === 'fulfilled' ? (teachers.value?.items || []) : [],
    reviewers: reviewers.status === 'fulfilled' ? (reviewers.value?.items || []) : [],
    failed: [subjects, teachers, reviewers].some((item) => item.status === 'rejected'),
  };
}

export function useReviewLookups() {
  const [lookups, setLookups] = useState(() => freshCache() || { subjects: [], teachers: [], reviewers: [], failed: false });

  useEffect(() => {
    if (freshCache()) return undefined;
    let active = true;
    lookupPromise = lookupPromise || loadLookups();
    lookupPromise.then((result) => {
      lookupPromise = null;
      if (!result.failed) {
        lookupCache = result;
        lookupCachedAt = Date.now();
      }
      if (active) setLookups(result);
    });
    return () => {
      active = false;
    };
  }, []);

  return useMemo(() => {
    const byId = (items) => new Map(items.map((item) => [refId(item), item]));
    return {
      ...lookups,
      subjectsById: byId(lookups.subjects),
      teachersById: byId(lookups.teachers),
      reviewersById: byId(lookups.reviewers),
    };
  }, [lookups]);
}

export function userName(option, fallback = '--') {
  return option?.display_name || option?.email || fallback;
}

/**
 * Chọn và nhận câu kế tiếp cho người duyệt:
 * ưu tiên câu đã giao/đang giữ của chính mình, sau đó tới câu chưa ai nhận theo độ ưu tiên.
 * Thử lần lượt vài ứng viên vì người khác có thể vừa nhận trước.
 */
export async function claimNextQuestion(user, { excludeId = '' } = {}) {
  const now = Date.now();
  // Không lọc "UNASSIGNED" ở API vì câu chưa từng được giao không có trường này.
  const [mine, open] = await Promise.all([
    listQuestions({ page: 1, pageSize: 20, reviewStatus: 'PENDING', assignedTo: 'me', sortBy: 'priority' }),
    listQuestions({ page: 1, pageSize: 50, reviewStatus: 'PENDING', sortBy: 'priority' }),
  ]);
  const seen = new Set();
  const candidates = [...(mine.items || []), ...(open.items || [])].filter((question) => {
    if (!question?.id || question.id === excludeId || seen.has(question.id)) return false;
    seen.add(question.id);
    return canClaim(question, user, now) && !isBlockedFromSecondary(question, user);
  });

  for (const question of candidates.slice(0, 5)) {
    const holdsLiveLock = question.review_assignment?.status === 'IN_REVIEW'
      && isAssignedToUser(question, user)
      && !isLockExpired(question, now);
    if (holdsLiveLock) return question;
    try {
      return await claimQuestionReview(question.id);
    } catch (error) {
      if (![403, 409, 400].includes(error?.status)) throw error;
    }
  }
  return null;
}

/**
 * Lấy toàn bộ câu chờ duyệt (tối đa 1.000 câu) để lọc phía trình duyệt những tiêu chí API chưa hỗ trợ,
 * ví dụ "gửi lại sau sửa".
 */
export async function fetchAllQuestions(query, limit = 1000) {
  const items = [];
  for (let page = 1; items.length < limit; page += 1) {
    const result = await listQuestions({ ...query, page, pageSize: 100 });
    const pageItems = result.items || [];
    items.push(...pageItems);
    if (!pageItems.length || items.length >= (result.total || 0)) break;
  }
  return items.slice(0, limit);
}
