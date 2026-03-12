<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../services/auth.js'
import Card from '../components/Card.vue'

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
  <div class="wrap">
    <Card>
      <h1 class="title">Welcome Back</h1>

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
    </Card>
  </div>
</template>

<style scoped>
.wrap {
  width: min(720px, 100%);
  margin: 0 auto;
  text-align: center;
}

.title {
  margin: 0 0 var(--space-5);
  font-size: 2.25rem;
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
  gap: var(--space-4);
  margin-bottom: var(--space-4);
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
  font-size: 0.9rem;
  opacity: 0.9;
}

.input {
  width: 100%;
  padding: 0.85rem 1rem;
  height: 48px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: transparent;
  color: inherit;
  outline: none;
  box-sizing: border-box;
  font-size: 1rem;
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
  padding: 0.8rem 1.2rem;
  height: 48px;
  width: 100%;
  max-width: 480px;
  box-sizing: border-box;
  background: var(--brand);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: 1rem;
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
  margin-top: var(--space-5);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: 0.95rem;
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
</style>
