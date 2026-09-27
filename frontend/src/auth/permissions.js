export const PERMISSIONS = Object.freeze({
  teacherWorkspace: Object.freeze(["Teacher"]),
  teacherAdminWorkspace: Object.freeze(["Teacher", "Admin"]),
  reviewerWorkspace: Object.freeze(["Reviewer", "Admin"]),
  adminWorkspace: Object.freeze(["Admin"]),
  authenticated: Object.freeze(["Admin", "Teacher", "Reviewer"]),
});

// Danh mục quyền, khớp backend core/dependencies.py. Mỗi quyền đều được kiểm tra thật ở backend.
// - Admin luôn có toàn bộ quyền; nhóm "Quản trị" chỉ thuộc vai trò Admin.
// - Giảng viên/Người duyệt: mặc định theo vai trò, có thể thêm hoặc bỏ từng quyền nghiệp vụ.
export const PERMISSION_GROUPS = Object.freeze([
  Object.freeze({
    id: "teacher",
    label: "Giảng viên",
    items: Object.freeze([
      { value: "questions.generate", label: "Sinh câu hỏi bằng AI", description: "Trang Sinh câu hỏi, chạy tác vụ sinh và lưu cấu hình sinh." },
      { value: "questions.manage_own", label: "Soạn và quản lý câu hỏi của mình", description: "Tạo, sửa, xoá, gửi duyệt câu hỏi do mình tạo." },
      { value: "documents.manage_own", label: "Quản lý tài liệu của mình", description: "Tải lên, OCR, sửa và xoá tài liệu do mình tải." },
      { value: "exams.manage_own", label: "Làm đề thi", description: "Tạo đề, ma trận đề, mã đề và xuất đề của mình." },
      { value: "catalog.subjects.manage_own", label: "Tạo và sửa học phần của mình", description: "Thêm học phần, chương, CLO cho học phần mình tạo." },
      { value: "questions.share_bank", label: "Chia sẻ câu hỏi và tài liệu", description: "Chia sẻ câu hỏi, tài liệu của mình cho người khác." },
      { value: "questions.use_shared_bank", label: "Dùng câu hỏi, tài liệu được chia sẻ", description: "Xem và dùng câu hỏi, tài liệu người khác chia sẻ." },
    ]),
  }),
  Object.freeze({
    id: "review",
    label: "Kiểm duyệt",
    items: Object.freeze([
      { value: "reviews.manage", label: "Kiểm duyệt câu hỏi", description: "Hộp việc, nhận câu, duyệt/yêu cầu sửa/từ chối và được giao câu." },
      { value: "questions.export_moodle", label: "Đưa câu đã duyệt lên Moodle", description: "Ghi câu hỏi đã duyệt vào Moodle (cần kèm quyền kiểm duyệt)." },
    ]),
  }),
  Object.freeze({
    id: "admin",
    label: "Quản trị (chỉ vai trò Quản trị viên)",
    adminOnly: true,
    items: Object.freeze([
      { value: "admin.overview", label: "Xem tổng quan" },
      { value: "admin.users", label: "Quản lý người dùng" },
      { value: "admin.catalog", label: "Quản lý học phần và cấu hình AI" },
      { value: "admin.jobs", label: "Quản lý tác vụ" },
      { value: "admin.moodle", label: "Quản lý Moodle" },
      { value: "admin.audit", label: "Xem nhật ký" },
      { value: "questions.manage_all", label: "Quản lý mọi câu hỏi" },
      { value: "documents.manage_all", label: "Quản lý mọi tài liệu" },
    ]),
  }),
]);

export const ALL_PERMISSIONS = Object.freeze(
  PERMISSION_GROUPS.flatMap((group) => group.items.map((item) => item.value)),
);
export const ASSIGNABLE_PERMISSIONS = Object.freeze(
  PERMISSION_GROUPS.filter((group) => !group.adminOnly).flatMap((group) => group.items.map((item) => item.value)),
);

export const ROLE_DEFAULT_PERMISSIONS = Object.freeze({
  Admin: ALL_PERMISSIONS,
  Teacher: Object.freeze(PERMISSION_GROUPS[0].items.map((item) => item.value)),
  Reviewer: Object.freeze(PERMISSION_GROUPS[1].items.map((item) => item.value)),
});

export const ROUTE_PERMISSION_KEYS = Object.freeze({
  "/sinh-cau-hoi": Object.freeze(["questions.generate"]),
  "/quan-ly": Object.freeze(["questions.manage_own"]),
  "/lam-de-thi": Object.freeze(["exams.manage_own"]),
  "/quan-ly-hoc-phan": Object.freeze(["catalog.subjects.manage_own"]),
  "/quan-ly-tai-lieu": Object.freeze(["documents.manage_own"]),
  "/lam-de-thi/:examId": Object.freeze(["exams.manage_own"]),
  "/kiem-duyet": Object.freeze(["reviews.manage"]),
  "/kiem-duyet/hieu-suat": Object.freeze(["reviews.manage"]),
  "/kiem-duyet/:questionId": Object.freeze(["reviews.manage"]),
  "/duyet-ai": Object.freeze(["admin.jobs"]),
  "/tong-quan": Object.freeze(["admin.overview"]),
  "/danh-muc": Object.freeze(["admin.catalog"]),
  "/cau-hinh-ai": Object.freeze(["admin.catalog"]),
  "/quan-ly-nguoi-dung": Object.freeze(["admin.users"]),
  "/nhat-ky-he-thong": Object.freeze(["admin.audit"]),
  "/quan-ly-job": Object.freeze(["admin.jobs"]),
  "/quan-ly-moodle": Object.freeze(["admin.moodle"]),
});

export const PROTECTED_ROUTE_ROLES = Object.freeze({
  "/sinh-cau-hoi": PERMISSIONS.teacherWorkspace,
  "/quan-ly": PERMISSIONS.teacherAdminWorkspace,
  "/lam-de-thi": PERMISSIONS.teacherAdminWorkspace,
  "/lam-de-thi/:examId": PERMISSIONS.teacherAdminWorkspace,
  "/quan-ly-hoc-phan": PERMISSIONS.teacherWorkspace,
  "/quan-ly-tai-lieu": PERMISSIONS.teacherAdminWorkspace,
  "/kiem-duyet": PERMISSIONS.reviewerWorkspace,
  "/kiem-duyet/hieu-suat": PERMISSIONS.reviewerWorkspace,
  "/kiem-duyet/:questionId": PERMISSIONS.reviewerWorkspace,
  "/duyet-ai": PERMISSIONS.adminWorkspace,
  "/tong-quan": PERMISSIONS.adminWorkspace,
  "/danh-muc": PERMISSIONS.adminWorkspace,
  "/cau-hinh-ai": PERMISSIONS.adminWorkspace,
  "/quan-ly-nguoi-dung": PERMISSIONS.adminWorkspace,
  "/nhat-ky-he-thong": PERMISSIONS.adminWorkspace,
  "/quan-ly-job": PERMISSIONS.adminWorkspace,
  "/quan-ly-moodle": PERMISSIONS.adminWorkspace,
  "/lich-cong-viec": PERMISSIONS.authenticated,
  "/ho-so": PERMISSIONS.authenticated,
});

export const ROLE_LANDING_PATHS = Object.freeze({
  Admin: "/tong-quan",
  Reviewer: "/kiem-duyet",
  Teacher: "/sinh-cau-hoi",
});

function splitPath(pathname) {
  return pathname.replace(/\/+$/, "").split("/").filter(Boolean);
}

export function pathMatches(pattern, pathname) {
  const patternParts = splitPath(pattern);
  const pathParts = splitPath(pathname);
  if (patternParts.length !== pathParts.length) return false;
  return patternParts.every((part, index) => (
    part.startsWith(":") || part === pathParts[index]
  ));
}

export function rolesForPath(pathname) {
  const entry = Object.entries(PROTECTED_ROUTE_ROLES).find(([pattern]) => (
    pathMatches(pattern, pathname)
  ));
  return entry?.[1] || null;
}

/**
 * Quyền thực tế của người dùng. Backend trả `permissions` là danh sách đã tính
 * (mặc định vai trò, trừ phần bị bỏ, cộng phần được thêm) nên dùng nguyên văn.
 */
export function permissionsForUser(userOrRole) {
  const role = typeof userOrRole === "string" ? userOrRole : userOrRole?.role;
  if (role === "Admin") return [...ALL_PERMISSIONS];
  if (typeof userOrRole !== "string" && Array.isArray(userOrRole?.permissions)) {
    // Quyền quản trị chỉ thuộc vai trò Admin.
    return userOrRole.permissions.filter((permission) => ASSIGNABLE_PERMISSIONS.includes(permission));
  }
  return [...(ROLE_DEFAULT_PERMISSIONS[role] || [])];
}

export function permissionsForPath(pathname) {
  const entry = Object.entries(ROUTE_PERMISSION_KEYS).find(([pattern]) => (
    pathMatches(pattern, pathname)
  ));
  return entry?.[1] || null;
}

export function canAccessPath(userOrRole, pathname) {
  const roles = rolesForPath(pathname);
  if (!roles) return true;
  const role = typeof userOrRole === "string" ? userOrRole : userOrRole?.role;
  if (!role) return false;
  // Quản trị viên có mọi quyền nhưng chỉ vào các trang dành cho khu quản trị.
  if (role === "Admin") return roles.includes("Admin");
  const requiredPermissions = permissionsForPath(pathname);
  // Trang không gắn quyền cụ thể (hồ sơ, lịch) đi theo vai trò.
  if (!requiredPermissions?.length) return roles.includes(role);
  // Còn lại theo quyền thực tế: bỏ quyền thì mất trang, được thêm quyền thì có trang.
  const permissions = permissionsForUser(userOrRole);
  return requiredPermissions.every((permission) => permissions.includes(permission));
}

export function landingPathForRole(role, requestedPath) {
  const requestedPathname = typeof requestedPath === "string"
    ? requestedPath.split("?")[0]
    : null;
  if (requestedPathname && canAccessPath(role, requestedPathname)) {
    return requestedPath;
  }
  return ROLE_LANDING_PATHS[role] || "/trang-chu";
}
