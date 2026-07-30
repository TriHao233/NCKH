import { useContext } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';
import Header from './Header';
import Footer from './Footer';
import './Layout.css';

const ADMIN_WORKSPACE_PATHS = [
    '/tong-quan',
    '/kiem-duyet',
    '/duyet-ai',
    '/quan-ly',
    '/lam-de-thi',
    '/danh-muc',
    '/quan-ly-nguoi-dung',
    '/quan-ly-job',
    '/quan-ly-moodle',
    '/nhat-ky-he-thong',
];

function Layout() {
    const { user } = useContext(AuthContext);
    const location = useLocation();
    const isAdminWorkspace = user?.role === 'Admin'
        && ADMIN_WORKSPACE_PATHS.some(
            (path) => location.pathname === path || location.pathname.startsWith(`${path}/`),
        );

    return (
        <div className={`app-shell ${isAdminWorkspace ? 'app-shell--admin' : ''}`}>
            <Header adminShell={isAdminWorkspace} />
            <main className={`page-main ${isAdminWorkspace ? 'page-main--admin' : ''}`}>
                <Outlet />
            </main>
            {!isAdminWorkspace && <Footer />}
        </div>
    );
}

export default Layout;
