import { useContext } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AboutPage from './pages/AboutPage';
import GeneratePage from './pages/GeneratePage';
import ManagePage from './pages/ManagePage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import AdminAiReviewPage from './pages/AdminAiReviewPage';
import AdminOverviewPage from './pages/AdminOverviewPage';
import CatalogAdminPage from './pages/CatalogAdminPage';
import AdminAuditPage from './pages/AdminAuditPage';
import AdminJobsPage from './pages/AdminJobsPage';
import AdminMoodlePage from './pages/AdminMoodlePage';
import UsersAdminPage from './pages/UsersAdminPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import GuidePage from './pages/GuidePage';
import ContactPage from './pages/ContactPage';
import UserProfile from './pages/UserProfile';
import TaskCalendarPage from './pages/TaskCalendarPage';
import ExamListPage from './pages/ExamListPage';
import ExamBuilderPage from './pages/ExamBuilderPage';
import { AuthContext } from './context/AuthContext';
import { canAccessPath } from './auth/permissions';

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
    );
}

export default App;
