<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '../services/auth.js'
import Card from '../components/Card.vue'

const router = useRouter()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const email = ref('')
const loading = ref(false)
const errorText = ref('')
const successText = ref('')

async function onSubmit() {
  errorText.value = ''
  successText.value = ''

  if (password.value !== confirmPassword.value) {
    errorText.value = 'Passwords do not match.'
    return
  }

  loading.value = true
  try {
    if (!email.value.trim()) {
      errorText.value = 'Email is required for password recovery.'
      loading.value = false
      return
    }

    const { status, body } = await register(
      username.value.trim(),
      password.value,
      email.value.trim(),
    )

    if (status === 201) {
      const token = body?.access_token
      const user = body?.username
      if (token) localStorage.setItem('access_token', token)
      if (user) localStorage.setItem('username', String(user))

      successText.value = `Welcome, ${body?.username || username.value}! Redirecting to login…`
      setTimeout(() => {
        router.push('/login')
      }, 1500)
    } else {
      // Show field-level or message-level errors
      if (body?.errors && typeof body.errors === 'object') {
        const msgs = Object.entries(body.errors).map(([k, v]) => `${k}: ${v}`)
        errorText.value = msgs.join('\n')
      } else {
        const msgMap = {
          username_already_exists: 'That username is already taken.',
          email_already_exists: 'That email address is already registered.',
          validation_error: 'Please check your inputs and try again.',
        }
        const raw = body?.message || ''
        errorText.value = msgMap[raw] || raw || `Error (HTTP ${status})`
      }
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
      <span class="brand-row"><span class="mark">🌍</span> Noosphere</span>
      <h1 class="title">Create Account</h1>

      <form class="form" @submit.prevent="onSubmit">
        <label class="field">
          <span class="label">Username <span class="required">*</span></span>
          <input
            v-model="username"
            class="input"
            placeholder="demo_user"
            autocomplete="username"
            :disabled="loading || !!successText"
          />
          <span class="hint">3–30 characters, letters/numbers/underscores, must start with a letter.</span>
        </label>

        <label class="field">
          <span class="label">Password <span class="required">*</span></span>
          <input
            v-model="password"
            class="input"
            type="password"
            placeholder="••••••••"
            autocomplete="new-password"
            :disabled="loading || !!successText"
          />
          <span class="hint">At least 8 characters with uppercase, lowercase, and a number.</span>
        </label>

        <label class="field">
          <span class="label">Confirm Password <span class="required">*</span></span>
          <input
            v-model="confirmPassword"
            class="input"
            type="password"
            placeholder="••••••••"
            autocomplete="new-password"
            :disabled="loading || !!successText"
          />
        </label>

        <label class="field">
          <span class="label">Email <span class="required">*</span></span>
          <input
            v-model="email"
            class="input"
            type="email"
            placeholder="you@example.com"
            autocomplete="email"
            :disabled="loading || !!successText"
            required
          />
          <span class="hint">Used for password recovery. Please provide a valid email address.</span>
        </label>

        <button class="btn" type="submit" :disabled="loading || !!successText">
          {{ loading ? 'Creating account…' : 'Register' }}
        </button>
      </form>

      <div v-if="successText" class="success">
        <span class="success-icon">✓</span> {{ successText }}
      </div>

      <div v-if="errorText" class="error">
        <span v-for="line in errorText.split('\n')" :key="line" class="error-line">{{ line }}</span>
      </div>

      <div class="links">
        <span class="link-text">Already have an account?</span>
        <RouterLink class="link" to="/login">Login</RouterLink>
      </div>
    </Card>
  </div>
</template>

<style scoped>
.wrap {
  width: min(720px, 100%);
  min-height: 100dvh;
  display: grid;
  align-content: center;
  text-align: center;
  margin: 0 auto;
  padding: var(--space-4) 0;
  box-sizing: border-box;
}

.brand-row {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.9rem;
  font-weight: 700;
  margin-bottom: var(--space-3);
}

.mark {
  color: var(--brand);
}

.title {
  margin: 0 0 var(--space-5);
  font-size: 2.25rem;
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
  gap: 0.3rem;
  text-align: left;
}

.label {
  font-size: 0.84rem;
  opacity: 0.9;
  font-weight: 500;
}

.required {
  color: #e05252;
  margin-left: 2px;
}

.optional {
  font-weight: 400;
  opacity: 0.55;
  font-size: 0.82rem;
  margin-left: 4px;
}

.hint {
  font-size: 0.78rem;
  opacity: 0.55;
  line-height: 1.4;
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
  display: block;
  margin-left: auto;
  margin-right: auto;
}

.btn:hover:not(:disabled) {
  background: var(--brand-600);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.success {
  margin-top: var(--space-3);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  border: 1px solid rgba(27, 156, 63, 0.4);
  background: color-mix(in oklab, rgba(27, 156, 63, 0.12) 80%, transparent);
  color: #1b9c3f;
  font-weight: 500;
  text-align: left;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.success-icon {
  font-size: 1.1rem;
  font-weight: 700;
}

.error {
  margin-top: var(--space-3);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 0, 0, 0.35);
  color: #ff9a9a;
  text-align: left;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
  display: grid;
  gap: 0.25rem;
}

.error-line {
  display: block;
  line-height: 1.5;
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
</style>
