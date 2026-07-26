import { useContext } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AboutPage from './pages/AboutPage';
import GeneratePage from './pages/GeneratePage';
import ManagePage from './pages/ManagePage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import CatalogAdminPage from './pages/CatalogAdminPage';
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

function RequireRole({ roles, children }) {
    const { user, loading } = useContext(AuthContext);
    const location = useLocation();
    if (loading) return <div className="route-loading">Đang kiểm tra phiên đăng nhập...</div>;
    if (!user) return <Navigate to="/dang-nhap" replace state={{ from: `${location.pathname}${location.search}` }} />;
    if (!roles.includes(user.role)) return <Navigate to="/trang-chu" replace />;
    return children;
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
                        <RequireRole roles={['Teacher']}>
                            <GeneratePage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/quan-ly"
                    element={(
                        <RequireRole roles={['Teacher']}>
                            <ManagePage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/lam-de-thi"
                    element={(
                        <RequireRole roles={['Teacher']}>
                            <ExamListPage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/lam-de-thi/:examId"
                    element={(
                        <RequireRole roles={['Teacher']}>
                            <ExamBuilderPage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/kiem-duyet"
                    element={(
                        <RequireRole roles={['Reviewer']}>
                            <ReviewQueuePage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/danh-muc"
                    element={(
                        <RequireRole roles={['Admin']}>
                            <CatalogAdminPage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/quan-ly-nguoi-dung"
                    element={(
                        <RequireRole roles={['Admin']}>
                            <UsersAdminPage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/lich-cong-viec"
                    element={(
                        <RequireRole roles={['Teacher']}>
                            <TaskCalendarPage />
                        </RequireRole>
                    )}
                />
                <Route path="/huong-dan" element={<GuidePage />} />
                <Route path="/lien-he" element={<ContactPage />} />
                <Route
                    path="/ho-so"
                    element={(
                        <RequireRole roles={['Admin', 'Teacher', 'Reviewer']}>
                            <UserProfile />
                        </RequireRole>
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
