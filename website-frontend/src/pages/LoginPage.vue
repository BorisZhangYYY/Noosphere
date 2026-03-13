<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../services/auth.js'

const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorText = ref('')
const needsEmailVerify = ref(false)

async function onSubmit() {
  errorText.value = ''
  needsEmailVerify.value = false
  loading.value = true

  try {
    const { status, body } = await login(username.value, password.value)

    if (status === 200) {
      const token = body?.access_token
      const user = body?.username
      if (token) localStorage.setItem('access_token', token)
      if (user) localStorage.setItem('username', String(user))

      if (body?.needs_email_verify) {
        needsEmailVerify.value = true
      }

      router.push('/home')
    } else if (status === 401) {
      errorText.value = 'Invalid username or password'
    } else {
      const msg = body?.message || body?.error || `Unexpected error (HTTP ${status})`
      errorText.value = String(msg)
    }
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-root">
    <section class="auth-left">
      <div class="left-inner">
        <span class="brand-row"><span class="mark">🌍</span> Noosphere</span>
        <h1 class="hero-title">Share what you know.</h1>
        <p class="hero-sub">A clean space for writing, curating, and learning with others.</p>
      </div>
    </section>

    <section class="auth-right">
      <div class="auth-card">
        <div v-if="needsEmailVerify" class="banner-warn">
          ⚠️ For your security, please verify your email address.
        </div>

        <form class="form" @submit.prevent="onSubmit">
          <label class="field">
            <span class="label">Username</span>
            <input
              v-model="username"
              class="input"
              placeholder="demo_user"
              autocomplete="username"
              :disabled="loading"
            />
          </label>

          <label class="field">
            <span class="label">Password</span>
            <input
              v-model="password"
              class="input"
              type="password"
              placeholder="••••••••"
              autocomplete="current-password"
              :disabled="loading"
            />
          </label>

          <button class="btn" type="submit" :disabled="loading">
            {{ loading ? 'Logging in…' : 'Login' }}
          </button>
        </form>

        <div v-if="errorText" class="error">{{ errorText }}</div>

        <div class="links">
          <RouterLink class="link" to="/forgot-password">Forgot password?</RouterLink>
          <span class="sep">·</span>
          <span class="link-text">Don't have an account?</span>
          <RouterLink class="link" to="/register">Register</RouterLink>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth-root {
  min-height: calc(100vh - 72px);
  display: grid;
  grid-template-columns: minmax(320px, 44%) minmax(0, 1fr);
  background: color-mix(in oklab, var(--bg) 46%, transparent);
}

.auth-left {
  border-right: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
  box-sizing: border-box;
}

.left-inner {
  width: min(380px, 100%);
}

.brand-row {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.92rem;
  font-weight: 700;
}

.mark {
  color: var(--brand);
}

.hero-title {
  margin: var(--space-4) 0 var(--space-3);
  font-size: 2.1rem;
  line-height: 1.12;
}

.hero-sub {
  margin: 0;
  opacity: 0.72;
  line-height: 1.65;
}

.auth-right {
  display: grid;
  place-items: center;
  padding: var(--space-6);
  box-sizing: border-box;
}

.auth-card {
  width: min(420px, 100%);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: 14px;
  background: var(--bg-elev);
  padding: var(--space-4);
  box-sizing: border-box;
}

.banner-warn {
  margin-bottom: var(--space-4);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 193, 7, 0.5);
  background: color-mix(in oklab, rgba(255, 193, 7, 0.15) 80%, transparent);
  color: #b8860b;
  font-weight: 500;
  text-align: left;
}

.form {
  display: grid;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  max-width: 480px;
  box-sizing: border-box;
  margin-left: auto;
  margin-right: auto;
}

.field {
  display: grid;
  gap: 0.35rem;
  text-align: left;
}

.label {
  font-size: 0.84rem;
  opacity: 0.9;
}

.input {
  width: 100%;
  padding: 0.64rem 0.86rem;
  height: 42px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: transparent;
  color: inherit;
  outline: none;
  box-sizing: border-box;
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.input:focus {
  border-color: var(--brand);
}

.input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn {
  padding: 0.64rem 0.96rem;
  height: 42px;
  width: 100%;
  max-width: 480px;
  box-sizing: border-box;
  background: var(--brand);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
}

.btn:hover:not(:disabled) {
  background: var(--brand-600);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error {
  margin-top: var(--space-3);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 0, 0, 0.35);
  color: #ff9a9a;
  text-align: left;
}

.links {
  margin-top: var(--space-3);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: 0.86rem;
  opacity: 0.9;
}

.link {
  color: var(--brand);
  text-decoration: none;
  font-weight: 500;
}

.link:hover {
  color: var(--brand-600);
  text-decoration: underline;
}

.link-text {
  color: inherit;
}

.sep {
  opacity: 0.4;
}

@media (max-width: 960px) {
  .auth-root {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-left {
    border-right: none;
    border-bottom: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
    padding: var(--space-5) var(--space-4);
  }

  .hero-title {
    font-size: 1.7rem;
  }

  .auth-right {
    padding: var(--space-4);
  }
}
</style>
