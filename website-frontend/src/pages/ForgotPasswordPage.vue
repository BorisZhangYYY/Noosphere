<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { sendEmailVerification, resetPassword } from '../services/auth.js'
import Card from '../components/Card.vue'

const router = useRouter()

// Step: 1 = email, 2 = otp, 3 = new password, 4 = success
const step = ref(1)

// Step 1
const email = ref('')
const step1Loading = ref(false)
const step1Error = ref('')

// Step 2
const otpCode = ref('')

// Step 3
const newPassword = ref('')
const confirmPassword = ref('')
const step3Loading = ref(false)
const step3Error = ref('')

async function onSendCode() {
  step1Error.value = ''
  if (!email.value.trim()) {
    step1Error.value = 'Please enter your email address.'
    return
  }
  step1Loading.value = true
  try {
    const { status, body } = await sendEmailVerification(email.value.trim())
    if (status >= 200 && status < 300) {
      step.value = 2
    } else {
      const msg = body?.message || body?.error || `Error (HTTP ${status})`
      step1Error.value = String(msg)
    }
  } catch (e) {
    step1Error.value = e instanceof Error ? e.message : String(e)
  } finally {
    step1Loading.value = false
  }
}

function onVerifyOtp() {
  if (!otpCode.value.trim()) return
  step.value = 3
}

function onResendCode() {
  otpCode.value = ''
  step3Error.value = ''
  step.value = 1
}

async function onResetPassword() {
  step3Error.value = ''

  if (!newPassword.value) {
    step3Error.value = 'Please enter a new password.'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    step3Error.value = 'Passwords do not match.'
    return
  }

  step3Loading.value = true
  try {
    const { status, body } = await resetPassword(
      email.value.trim(),
      otpCode.value.trim(),
      newPassword.value,
    )
    if (status >= 200 && status < 300) {
      step.value = 4
    } else {
      const msg = body?.message || body?.error || `Error (HTTP ${status})`
      step3Error.value = String(msg)
    }
  } catch (e) {
    step3Error.value = e instanceof Error ? e.message : String(e)
  } finally {
    step3Loading.value = false
  }
}

function goToLogin() {
  router.push('/login')
}
</script>

<template>
  <div class="wrap">
    <Card>
      <span class="brand-row"><span class="mark">🌍</span> Noosphere</span>
      <!-- Step indicator -->
      <div class="stepper">
        <div
          v-for="n in 3"
          :key="n"
          class="step-dot"
          :class="{
            active: step === n,
            done: step > n,
            success: step === 4,
          }"
        >
          <span v-if="step > n && step !== 4" class="check">✓</span>
          <span v-else>{{ n }}</span>
        </div>
      </div>

      <!-- ─── Step 1: Email ─── -->
      <template v-if="step === 1">
        <h1 class="title">Reset Password</h1>
        <p class="subtitle">Step 1: Verify your email</p>

        <form class="form" @submit.prevent="onSendCode">
          <label class="field">
            <span class="label">Email address</span>
            <input
              v-model="email"
              class="input"
              type="email"
              placeholder="you@example.com"
              autocomplete="email"
              :disabled="step1Loading"
            />
          </label>

          <button class="btn" type="submit" :disabled="step1Loading">
            {{ step1Loading ? 'Sending…' : 'Send Verification Code' }}
          </button>
        </form>

        <div v-if="step1Error" class="error">{{ step1Error }}</div>

        <div class="links">
          <span class="link-text">Remember your password?</span>
          <RouterLink class="link" to="/login">Back to Login</RouterLink>
        </div>
      </template>

      <!-- ─── Step 2: OTP ─── -->
      <template v-else-if="step === 2">
        <h1 class="title">Reset Password</h1>
        <p class="subtitle">Step 2: Enter verification code</p>

        <div class="info-pill">
          <span class="info-icon">📧</span>
          <span>Code sent to: <strong>{{ email }}</strong></span>
        </div>

        <form class="form" @submit.prevent="onVerifyOtp">
          <label class="field">
            <span class="label">6-digit verification code</span>
            <input
              v-model="otpCode"
              class="input otp-input"
              type="text"
              inputmode="numeric"
              pattern="[0-9]*"
              maxlength="6"
              placeholder="123456"
              autocomplete="one-time-code"
            />
          </label>

          <button class="btn" type="submit" :disabled="otpCode.trim().length === 0">
            Verify Code
          </button>
        </form>

        <div class="links">
          <span class="link-text">Didn't receive it?</span>
          <button class="link-btn" type="button" @click="onResendCode">Resend code</button>
        </div>
      </template>

      <!-- ─── Step 3: New Password ─── -->
      <template v-else-if="step === 3">
        <h1 class="title">Reset Password</h1>
        <p class="subtitle">Step 3: Set new password</p>

        <form class="form" @submit.prevent="onResetPassword">
          <label class="field">
            <span class="label">New Password</span>
            <input
              v-model="newPassword"
              class="input"
              type="password"
              placeholder="••••••••"
              autocomplete="new-password"
              :disabled="step3Loading"
            />
          </label>

          <label class="field">
            <span class="label">Confirm Password</span>
            <input
              v-model="confirmPassword"
              class="input"
              type="password"
              placeholder="••••••••"
              autocomplete="new-password"
              :disabled="step3Loading"
            />
          </label>

          <button class="btn" type="submit" :disabled="step3Loading">
            {{ step3Loading ? 'Resetting…' : 'Reset Password' }}
          </button>
        </form>

        <div v-if="step3Error" class="error">{{ step3Error }}</div>
      </template>

      <!-- ─── Step 4: Success ─── -->
      <template v-else-if="step === 4">
        <div class="success-wrap">
          <div class="success-icon">🎉</div>
          <h1 class="title">All done!</h1>
          <p class="success-msg">Password reset successfully!</p>
          <p class="success-sub">You can now log in with your new password.</p>
          <button class="btn" type="button" @click="goToLogin">Back to Login</button>
        </div>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.wrap {
  width: min(720px, 100%);
  min-height: 100dvh;
  display: grid;
  align-content: center;
  margin: 0 auto;
  text-align: center;
  padding: var(--space-4) 0;
  box-sizing: border-box;
}

.brand-row {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.9rem;
  font-weight: 700;
  margin-bottom: var(--space-4);
}

.mark {
  color: var(--brand);
}

/* ── Stepper ── */
.stepper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.step-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 700;
  border: 2px solid color-mix(in oklab, var(--border) 80%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 70%, transparent);
  color: var(--text);
  transition: background 0.25s, border-color 0.25s, color 0.25s;
  user-select: none;
}

.step-dot.active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--brand) 30%, transparent);
}

.step-dot.done {
  background: color-mix(in oklab, var(--brand) 20%, transparent);
  border-color: var(--brand);
  color: var(--brand);
}

.check {
  font-size: 0.9rem;
}

/* ── Typography ── */
.title {
  margin: 0 0 var(--space-2);
  font-size: 2rem;
}

.subtitle {
  margin: 0 0 var(--space-5);
  opacity: 0.75;
  font-size: 0.95rem;
}

/* ── Info pill ── */
.info-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0.6rem 1rem;
  border-radius: var(--radius-md);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 65%, transparent);
  font-size: 0.9rem;
  margin-bottom: var(--space-4);
}

.info-icon {
  font-size: 1rem;
}

/* ── Form ── */
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

.otp-input {
  text-align: center;
  font-size: 1.75rem;
  letter-spacing: 0.5em;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Courier New', monospace;
}

/* ── Button ── */
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

/* ── Error ── */
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
}

/* ── Links row ── */
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

.link-btn {
  background: none;
  border: none;
  padding: 0;
  color: var(--brand);
  font-weight: 500;
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
  text-decoration: none;
  height: auto;
}

.link-btn:hover {
  color: var(--brand-600);
  text-decoration: underline;
  border-color: transparent;
}

/* ── Success state ── */
.success-wrap {
  display: grid;
  place-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
}

.success-icon {
  font-size: 3.5rem;
  line-height: 1;
}

.success-msg {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: #1b9c3f;
}

.success-sub {
  margin: 0;
  opacity: 0.75;
  font-size: 0.95rem;
}

.success-wrap .btn {
  margin-top: var(--space-3);
}
</style>
