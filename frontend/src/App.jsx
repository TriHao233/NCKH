import { useContext } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
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
import { AuthContext } from './context/AuthContext';

function RequireRole({ roles, children }) {
    const { user, loading } = useContext(AuthContext);
    if (loading) return null;
    if (!user) return <Navigate to="/dang-nhap" replace />;
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
                        <RequireRole roles={['Admin', 'Teacher']}>
                            <GeneratePage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/quan-ly"
                    element={(
                        <RequireRole roles={['Admin', 'Teacher', 'Reviewer']}>
                            <ManagePage />
                        </RequireRole>
                    )}
                />
                <Route
                    path="/kiem-duyet"
                    element={(
                        <RequireRole roles={['Admin', 'Reviewer']}>
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
                <Route path="/huong-dan" element={<GuidePage />} />
                <Route path="/lien-he" element={<ContactPage />} />
                <Route path="/ho-so" element={<UserProfile />} />
            </Route>

            <Route path="/dang-nhap" element={<LoginPage />} />
            <Route path="/dang-ky" element={<RegisterPage />} />
            <Route path="*" element={<Navigate to="/trang-chu" replace />} />
        </Routes>
    );
}

export default App;
