// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyDDPsHgdDyAbyNL4pTQUUInyw9s4VMQVeM",
  authDomain: "nckh-c0ef6.firebaseapp.com",
  projectId: "nckh-c0ef6",
  storageBucket: "nckh-c0ef6.firebasestorage.app",
  messagingSenderId: "953198341983",
  appId: "1:953198341983:web:22a5e6810096bca9be10ea",
  measurementId: "G-BV5PSNEMVP"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
export const analytics = getAnalytics(app);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });