import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AboutPage from './pages/AboutPage';
import GeneratePage from './pages/GeneratePage';
import ManagePage from './pages/ManagePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import GuidePage from './pages/GuidePage';
import ContactPage from './pages/ContactPage';

function App() {
    return (
        <Routes>
            <Route element={<Layout />}>
                <Route path="/" element={<Navigate to="/trang-chu" replace />} />
                <Route path="/trang-chu" element={<HomePage />} />
                <Route path="/gioi-thieu" element={<AboutPage />} />
                <Route path="/sinh-cau-hoi" element={<GeneratePage />} />
                <Route path="/quan-ly" element={<ManagePage />} />
                <Route path="/huong-dan" element={<GuidePage />} />
                <Route path="/lien-he" element={<ContactPage />} />
            </Route>

            <Route path="/dang-nhap" element={<LoginPage />} />
            <Route path="/dang-ky" element={<RegisterPage />} />
            <Route path="*" element={<Navigate to="/trang-chu" replace />} />
        </Routes>
    );
}

export default App;
