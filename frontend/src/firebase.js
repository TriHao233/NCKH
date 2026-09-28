import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

export const CANONICAL_FIREBASE_PROJECT_ID = "nckh-e6817";

const firebaseConfig = {
  apiKey: "AIzaSyCA0WPy--PUOvHcgQgDQRYCqgaeSy029_E",
  authDomain: "nckh-e6817.firebaseapp.com",
  projectId: CANONICAL_FIREBASE_PROJECT_ID,
  storageBucket: "nckh-e6817.firebasestorage.app",
  messagingSenderId: "920272280208",
  appId: "1:920272280208:web:454fd58bf1f15b58479615",
  measurementId: "G-ZLLP495N0E",
};

const app = initializeApp(firebaseConfig);
const hasFirebaseWebConfig = Boolean(firebaseConfig.apiKey && firebaseConfig.appId);
const usesRegisterProject = firebaseConfig.projectId === CANONICAL_FIREBASE_PROJECT_ID;

let authInstance = null;
let analyticsInstance = null;
let googleProviderInstance = null;

if (hasFirebaseWebConfig && usesRegisterProject) {
  try {
    authInstance = getAuth(app);
    analyticsInstance = firebaseConfig.measurementId ? getAnalytics(app) : null;
    googleProviderInstance = new GoogleAuthProvider();
    googleProviderInstance.setCustomParameters({ prompt: "select_account" });
  } catch (error) {
    console.error("Firebase web app config is invalid for nckh-e6817.", error);
  }
}

export const isFirebaseConfigured = Boolean(authInstance);
export const analytics = analyticsInstance;
export const auth = authInstance;
export const googleProvider = googleProviderInstance;
