// frontend/firebase.js
import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth"; // Thêm GoogleAuthProvider

const firebaseConfig = {
  apiKey: "AIzaSyCA0WPy--PUOvHcgQgDQRYCqgaeSy029_E",
  authDomain: "nckh-e6817.firebaseapp.com",
  projectId: "nckh-e6817",
  storageBucket: "nckh-e6817.firebasestorage.app",
  messagingSenderId: "920272280208",
  appId: "1:920272280208:web:454fd58bf1f15b58479615",
  measurementId: "G-ZLLP495N0E"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider(); // Thêm dòng này
googleProvider.setCustomParameters({ prompt: "select_account" });
