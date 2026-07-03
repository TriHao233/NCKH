import { createContext, useState, useEffect } from 'react';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Kiểm tra token khi ứng dụng khởi chạy
        const token = localStorage.getItem("token");
        const userInfo = localStorage.getItem("userInfo");
        if (token && userInfo) {
            setUser(JSON.parse(userInfo));
        }
        setLoading(false);
    }, []);

    const login = (token, userInfo) => {
        localStorage.setItem("token", token);
        localStorage.setItem("userInfo", JSON.stringify(userInfo));
        setUser(userInfo);
    };

    const logout = () => {
        localStorage.removeItem("token");
        localStorage.removeItem("userInfo");
        setUser(null);
    };

    // Cập nhật thông tin user hiện tại (VD: sau khi chỉnh sửa hồ sơ) mà không đổi token
    const updateUser = (userInfo) => {
        localStorage.setItem("userInfo", JSON.stringify(userInfo));
        setUser(userInfo);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, updateUser, loading }}>
            {children}
        </AuthContext.Provider>
    );
};