import { auth } from "../../firebase";
import { notifyAuthFailure } from "../auth/authFailure";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export async function apiRequest(
  path,
  {
    method = "GET",
    body,
    headers = {},
    authRequired = true,
    signal,
    _retriedAfterRefresh = false,
  } = {},
) {
  const requestHeaders = { Accept: "application/json", ...headers };
  if (body !== undefined && !(body instanceof FormData)) {
    requestHeaders["Content-Type"] = "application/json";
  }

  if (authRequired) {
    await auth.authStateReady();
    const firebaseUser = auth.currentUser;
    if (!firebaseUser) {
      throw new ApiError("Bạn chưa đăng nhập", 401, null);
    }
    requestHeaders.Authorization = `Bearer ${await firebaseUser.getIdToken()}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: requestHeaders,
    body:
      body === undefined || body instanceof FormData
        ? body
        : JSON.stringify(body),
    signal,
  });

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const rawText = response.status === 204 ? "" : await response.text();
  let payload = rawText;
  if (isJson && rawText) {
    payload = JSON.parse(rawText);
  } else if (isJson) {
    payload = null;
  }
  if (!response.ok) {
    if (
      authRequired
      && response.status === 401
      && !_retriedAfterRefresh
      && auth.currentUser
    ) {
      try {
        await auth.currentUser.getIdToken(true);
      } catch {
        notifyAuthFailure(401, payload);
        throw new ApiError(
          "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
          401,
          payload,
        );
      }
      return apiRequest(path, {
        method,
        body,
        headers,
        authRequired,
        signal,
        _retriedAfterRefresh: true,
      });
    }
    if (authRequired) {
      notifyAuthFailure(response.status, payload);
    }
    throw new ApiError(
      payload?.detail || payload?.message || "Yêu cầu API thất bại",
      response.status,
      payload,
    );
  }
  return payload;
}
