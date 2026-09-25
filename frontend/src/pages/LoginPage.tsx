import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { LockKey } from "@phosphor-icons/react";
import { api } from "../api";
import { Atmosphere } from "../components/Atmosphere";

export function LoginPage() {
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: api.login,
    onSuccess: () => {
      setPassword("");
      queryClient.setQueryData(["auth-status"], { required: true, authenticated: true });
      void queryClient.invalidateQueries({ predicate: query => query.queryKey[0] !== "auth-status" });
    }
  });

  return (
    <main className="login-page">
      <Atmosphere />
      <form
        className="login-card"
        onSubmit={(event) => {
          event.preventDefault();
          if (password) login.mutate(password);
        }}
      >
        <img className="login-mark" src="/app/noosphere-mark.svg" alt="" />
        <h1>Noosphere</h1>
        <p className="login-description">
          {zh ? "输入访问令牌进入你的知识工作区。" : "Enter your access token to open your knowledge workspace."}
        </p>
        <label className="login-field">
          <span>{zh ? "访问令牌" : "Access token"}</span>
          <div className="login-input-wrap">
            <LockKey size={16} />
            <input
              type="password"
              value={password}
              onChange={(event) => { setPassword(event.target.value); login.reset(); }}
              placeholder={zh ? "NOOSPHERE_ACCESS_TOKEN" : "NOOSPHERE_ACCESS_TOKEN"}
              autoFocus
              autoComplete="current-password"
            />
          </div>
        </label>
        {login.isError && (
          <p className="login-error" role="alert">
            {zh ? "令牌不正确，请检查后重试。" : "Incorrect token. Check it and try again."}
          </p>
        )}
        <button className="button-primary login-submit" type="submit" disabled={!password || login.isPending}>
          {login.isPending ? (zh ? "正在登录…" : "Signing in…") : (zh ? "登录" : "Sign in")}
        </button>
      </form>
    </main>
  );
}
