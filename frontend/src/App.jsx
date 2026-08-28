import { lazy, Suspense, useContext } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import { AuthContext } from './context/AuthContext';
import { canAccessPath } from './auth/permissions';

const AboutPage = lazy(() => import('./pages/AboutPage'));
const GeneratePage = lazy(() => import('./pages/GeneratePage'));
const ManagePage = lazy(() => import('./pages/ManagePage'));
const ReviewQueuePage = lazy(() => import('./pages/ReviewQueuePage'));
const AdminAiReviewPage = lazy(() => import('./pages/AdminAiReviewPage'));
const AdminOverviewPage = lazy(() => import('./pages/AdminOverviewPage'));
const CatalogAdminPage = lazy(() => import('./pages/CatalogAdminPage'));
const AdminAuditPage = lazy(() => import('./pages/AdminAuditPage'));
const AdminJobsPage = lazy(() => import('./pages/AdminJobsPage'));
const AdminMoodlePage = lazy(() => import('./pages/AdminMoodlePage'));
const UsersAdminPage = lazy(() => import('./pages/UsersAdminPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const RegisterPage = lazy(() => import('./pages/RegisterPage'));
const GuidePage = lazy(() => import('./pages/GuidePage'));
const ContactPage = lazy(() => import('./pages/ContactPage'));
const UserProfile = lazy(() => import('./pages/UserProfile'));
const TaskCalendarPage = lazy(() => import('./pages/TaskCalendarPage'));
const ExamListPage = lazy(() => import('./pages/ExamListPage'));
const SubjectManage = lazy(() => import('./pages/SubjectManage'));
const ExamBuilderPage = lazy(() => import('./pages/ExamBuilderPage'));

function RequireAccess({ path, children }) {
    const { user, loading } = useContext(AuthContext);
    const location = useLocation();
    if (loading) return <div className="route-loading">Đang kiểm tra phiên đăng nhập...</div>;
    if (!user) return <Navigate to="/dang-nhap" replace state={{ from: `${location.pathname}${location.search}` }} />;
    if (!canAccessPath(user, path)) return <Navigate to="/trang-chu" replace />;
    return children;
}

function ProtectedPage({ path, children }) {
    return (
        <RequireAccess path={path}>
            {children}
        </RequireAccess>
    );
}

function App() {
    return (
      <Suspense fallback={<div className="route-loading">Đang tải trang...</div>}>
        <Routes>
            <Route element={<Layout />}>
                <Route path="/" element={<Navigate to="/trang-chu" replace />} />
                <Route path="/trang-chu" element={<HomePage />} />
                <Route path="/gioi-thieu" element={<AboutPage />} />
                <Route
                    path="/sinh-cau-hoi"
                    element={(
                        <ProtectedPage path="/sinh-cau-hoi">
                            <GeneratePage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/quan-ly"
                    element={(
                        <ProtectedPage path="/quan-ly">
                            <ManagePage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/quan-ly-hoc-phan"
                    element={(
                        <ProtectedPage path="/quan-ly-hoc-phan">
                            <SubjectManage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/lam-de-thi"
                    element={(
                        <ProtectedPage path="/lam-de-thi">
                            <ExamListPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/lam-de-thi/:examId"
                    element={(
                        <ProtectedPage path="/lam-de-thi/:examId">
                            <ExamBuilderPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/kiem-duyet"
                    element={(
                        <ProtectedPage path="/kiem-duyet">
                            <ReviewQueuePage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/duyet-ai"
                    element={(
                        <ProtectedPage path="/duyet-ai">
                            <AdminAiReviewPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/tong-quan"
                    element={(
                        <ProtectedPage path="/tong-quan">
                            <AdminOverviewPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/danh-muc"
                    element={(
                        <ProtectedPage path="/danh-muc">
                            <CatalogAdminPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/quan-ly-nguoi-dung"
                    element={(
                        <ProtectedPage path="/quan-ly-nguoi-dung">
                            <UsersAdminPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/nhat-ky-he-thong"
                    element={(
                        <ProtectedPage path="/nhat-ky-he-thong">
                            <AdminAuditPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/quan-ly-job"
                    element={(
                        <ProtectedPage path="/quan-ly-job">
                            <AdminJobsPage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/quan-ly-moodle"
                    element={(
                        <ProtectedPage path="/quan-ly-moodle">
                            <AdminMoodlePage />
                        </ProtectedPage>
                    )}
                />
                <Route
                    path="/lich-cong-viec"
                    element={(
                        <ProtectedPage path="/lich-cong-viec">
                            <TaskCalendarPage />
                        </ProtectedPage>
                    )}
                />
                <Route path="/huong-dan" element={<GuidePage />} />
                <Route path="/lien-he" element={<ContactPage />} />
                <Route
                    path="/ho-so"
                    element={(
                        <ProtectedPage path="/ho-so">
                            <UserProfile />
                        </ProtectedPage>
                    )}
                />
            </Route>

            <Route path="/dang-nhap" element={<LoginPage />} />
            <Route path="/dang-ky" element={<RegisterPage />} />
            <Route path="*" element={<Navigate to="/trang-chu" replace />} />
        </Routes>
      </Suspense>
    );
}

export default App;
