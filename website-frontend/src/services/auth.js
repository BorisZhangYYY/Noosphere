import { http } from "./http.js";

export async function register(username, password, email) {
  const body = { username, password };
  if (email) body.email = email;
  const res = await http.post("/api/auth/register", body);
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

export async function login(username, password) {
  const res = await http.post("/api/auth/login", { username, password });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

export async function logout(token) {
  const res = await http.post(
    "/api/auth/logout",
    {},
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

export async function sendEmailVerification(email) {
  const res = await http.post("/api/auth/email_verifying", { email });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

export async function resetPassword(email, otp_code, new_password) {
  const res = await http.post("/api/auth/reset_success", {
    email,
    otp_code,
    new_password,
  });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}
