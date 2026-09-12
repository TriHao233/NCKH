import { createContext, useState, useEffect, useRef } from 'react';
import { onIdTokenChanged, signOut } from 'firebase/auth';

import { auth } from '../firebase';
import { clearDemoSession, readDemoSession, saveDemoSession } from '../auth/demoSession';
import { apiRequest } from '../services/apiClient';

export const AuthContext = createContext();

// Keyed by uid (not object reference) so the explicit login() call and the
// onIdTokenChanged listener dedupe onto the same in-flight request, even
// when Firebase hands them different User object instances.
const sessionSyncs = new Map();

function readCachedUser() {
    const cachedUser = localStorage.getItem("userInfo");
    if (!cachedUser) return null;
    try {
        return JSON.parse(cachedUser);
    } catch {
        localStorage.removeItem("userInfo");
        return null;
    }
}

function syncBackendSession(firebaseUser, { forceRefresh = false } = {}) {
    const existing = sessionSyncs.get(firebaseUser.uid);
    if (existing && !forceRefresh) return existing;

    const syncPromise = firebaseUser.getIdToken(forceRefresh)
        .then((idToken) =>
            apiRequest("/auth/login", {
                method: "POST",
                body: { id_token: idToken },
                authRequired: false,
            }).then((data) => data.user)
        )
        .finally(() => {
            if (sessionSyncs.get(firebaseUser.uid) === syncPromise) {
                sessionSyncs.delete(firebaseUser.uid);
            }
        });
    sessionSyncs.set(firebaseUser.uid, syncPromise);
    return syncPromise;
}

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(() => readCachedUser());
    const [loading, setLoading] = useState(true);
    const authGeneration = useRef(0);

    const persistUser = (userInfo) => {
        localStorage.setItem("userInfo", JSON.stringify(userInfo));
        setUser(userInfo);
    };

    useEffect(() => {
        // Firebase is the source of truth for session persistence and token refresh.
        let active = true;
        if (!auth) {
            const demoSession = readDemoSession();
            if (demoSession?.user) {
                localStorage.setItem("userInfo", JSON.stringify(demoSession.user));
                setUser(demoSession.user);
            } else {
                localStorage.removeItem("userInfo");
                setUser(null);
            }
            setLoading(false);
            return () => {
                active = false;
            };
        }
        const unsubscribe = onIdTokenChanged(auth, async (firebaseUser) => {
            const generation = ++authGeneration.current;
            if (!firebaseUser) {
                const demoSession = readDemoSession();
                if (demoSession?.user) {
                    localStorage.setItem("userInfo", JSON.stringify(demoSession.user));
                    if (active) {
                        setUser(demoSession.user);
                        setLoading(false);
                    }
                    return;
                }
                localStorage.removeItem("userInfo");
                if (active) {
                    setUser(null);
                    setLoading(false);
                }
                return;
            }

            setLoading(true);
            clearDemoSession();
            const cachedUser = readCachedUser();
            if (cachedUser?.firebase_uid === firebaseUser.uid) {
                setUser(cachedUser);
            } else {
                setUser(null);
            }
            try {
                const syncedUser = await syncBackendSession(firebaseUser);
                if (
                    active
                    && generation === authGeneration.current
                    && auth.currentUser?.uid === firebaseUser.uid
                ) {
                    persistUser(syncedUser);
                }
            } catch (error) {
                if (!active || generation !== authGeneration.current) return;
                if (error?.status === 401 || error?.status === 403) {
                    // A single 401 can be a transient race (stale cached token from a
                    // concurrent sync); retry once with a forced token refresh before
                    // treating it as a real auth failure.
                    try {
                        const syncedUser = await syncBackendSession(firebaseUser, { forceRefresh: true });
                        if (
                            active
                            && generation === authGeneration.current
                            && auth.currentUser?.uid === firebaseUser.uid
                        ) {
                            persistUser(syncedUser);
                        }
                        return;
                    } catch (retryError) {
                        if (!active || generation !== authGeneration.current) return;
                        if (retryError?.status === 401 || retryError?.status === 403) {
                            await signOut(auth);
                        }
                        return;
                    }
                }
                const fallbackUser = readCachedUser();
                if (fallbackUser?.firebase_uid === firebaseUser.uid) {
                    setUser(fallbackUser);
                } else if (fallbackUser) {
                    localStorage.removeItem("userInfo");
                }
            } finally {
                if (active && generation === authGeneration.current) {
                    setLoading(false);
                }
            }
        });
        return () => {
            active = false;
            unsubscribe();
        };
    }, []);

    const login = async (firebaseUser) => {
        if (!auth) {
            throw new Error("Firebase web app chưa được cấu hình");
        }
        clearDemoSession();
        const syncedUser = await syncBackendSession(firebaseUser);
        if (auth.currentUser?.uid !== firebaseUser.uid) {
            throw new Error("Phiên Firebase đã thay đổi");
        }
        persistUser(syncedUser);
        return syncedUser;
    };

    const loginWithDemoSession = async ({ demo_token: demoToken, user: demoUser }) => {
        if (!demoToken || !demoUser) {
            throw new Error("Phiên demo không hợp lệ");
        }
        saveDemoSession(demoToken, demoUser);
        persistUser(demoUser);
        return demoUser;
    };

    const logout = async () => {
        try {
            await apiRequest("/auth/logout", { method: "POST" });
        } catch {
            // Firebase sign-out must still complete if the API is unavailable.
        } finally {
            clearDemoSession();
            if (auth) {
                await signOut(auth);
            }
            localStorage.removeItem("userInfo");
            setUser(null);
        }
    };

    // Cập nhật thông tin user hiện tại (VD: sau khi chỉnh sửa hồ sơ) mà không đổi token
    const updateUser = (userInfo) => {
        persistUser(userInfo);
    };

    return (
        <AuthContext.Provider value={{ user, login, loginWithDemoSession, logout, updateUser, loading }}>
            {children}
        </AuthContext.Provider>
    );
};
