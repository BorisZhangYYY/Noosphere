<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const panelOpen = ref(false)
const blur = ref(false)
const dim = ref(0.15)
const preset = ref('violet-pink')
const customBg = ref('')   // base64 data-url or ''

const fabWrapRef = ref(null)

// ── Persistence ────────────────────────────────────────────────────────────
function loadPrefs() {
  blur.value   = (localStorage.getItem('hk_bg_blur')   || 'false') === 'true'
  const d      = parseFloat(localStorage.getItem('hk_bg_dim') || '0.15')
  dim.value    = Number.isFinite(d) ? d : 0.15
  preset.value = localStorage.getItem('hk_bg_preset')  || 'violet-pink'
  customBg.value = localStorage.getItem('hk_bg_custom') || ''
}

function persist() {
  localStorage.setItem('hk_bg_blur',   String(blur.value))
  localStorage.setItem('hk_bg_dim',    String(dim.value))
  localStorage.setItem('hk_bg_preset', preset.value)
  // customBg is saved separately (potentially large)
}

function resetTheme() {
  preset.value   = 'violet-pink'
  blur.value     = false
  dim.value      = 0.15
  customBg.value = ''
  localStorage.removeItem('hk_bg_custom')
  persist()
}

// ── Custom image upload ─────────────────────────────────────────────────────
const fileInputRef = ref(null)

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) return

  const reader = new FileReader()
  reader.onload = (ev) => {
    const result = ev.target?.result
    if (typeof result === 'string') {
      customBg.value = result
      preset.value   = 'custom'
      try {
        localStorage.setItem('hk_bg_custom', result)
        localStorage.setItem('hk_bg_preset', 'custom')
      } catch {
        // localStorage quota exceeded (large image) — keep in memory only
      }
    }
  }
  reader.readAsDataURL(file)
  // reset so the same file can be re-selected
  e.target.value = ''
}

function removeCustomBg() {
  customBg.value = ''
  preset.value   = 'violet-pink'
  localStorage.removeItem('hk_bg_custom')
  localStorage.setItem('hk_bg_preset', 'violet-pink')
}

// ── Background style ────────────────────────────────────────────────────────
const GRADIENTS = {
  'violet-pink': 'linear-gradient(135deg, #5f2eea 0%, #a4508b 45%, #ff6ec4 100%)',
  'blue-cyan':   'linear-gradient(135deg, #3a7bd5 0%, #00d2ff 100%)',
  'sunset':      'linear-gradient(135deg, #f6d365 0%, #fda085 100%)',
  'forest':      'linear-gradient(135deg, #134e5e 0%, #71b280 100%)',
  'midnight':    'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
}

const bgStyle = computed(() => {
  const styles = {}
  if (preset.value === 'custom' && customBg.value) {
    styles.backgroundImage = `url(${customBg.value})`
    styles.backgroundSize     = 'cover'
    styles.backgroundPosition = 'center'
  } else {
    styles.backgroundImage = GRADIENTS[preset.value] || GRADIENTS['violet-pink']
  }
  styles.filter = blur.value ? 'blur(8px) saturate(1.05)' : 'none'
  return styles
})

const overlayStyle = computed(() => ({
  background: `rgba(0,0,0,${dim.value})`,
}))

// ── Click-outside to close panel ────────────────────────────────────────────
function onDocClick(e) {
  if (!panelOpen.value) return
  if (fabWrapRef.value && !fabWrapRef.value.contains(e.target)) {
    panelOpen.value = false
  }
}

onMounted(() => {
  loadPrefs()
  document.addEventListener('click', onDocClick, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick, true)
})
</script>

<template>
  <div class="shell">
    <div class="bg" :style="bgStyle"></div>
    <div class="bg-overlay" :style="overlayStyle"></div>

    <header class="header">
      <div class="head">
        <div class="head-card">
          <div class="brand">Hot Knowledge</div>
        </div>
      </div>
    </header>

    <main class="main">
      <slot />
    </main>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      style="display:none"
      @change="onFileChange"
    />

    <!-- FAB + Settings panel -->
    <div ref="fabWrapRef" class="fab-wrap">
      <button
        class="fab"
        :class="{ active: panelOpen }"
        title="Background & Theme"
        @click.stop="panelOpen = !panelOpen"
      >
        <svg class="fab-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="currentColor"
            d="M12 3a9 9 0 1 0 0 18A9 9 0 0 0 12 3Zm0 2a7 7 0 0 1 6.33 4H5.67A7 7 0 0 1 12 5Zm-7 7a7 7 0 0 1 .12-1.3h.01l3.18 5.5A7 7 0 0 1 5 12Zm7 7a6.97 6.97 0 0 1-3.6-1H12a3 3 0 1 0 0-6 3 3 0 0 0-2.83 2H5.67A7 7 0 0 1 19 12a7 7 0 0 1-7 7Z"
          />
        </svg>
      </button>

      <Transition name="panel">
        <div v-if="panelOpen" class="panel" @click.stop>
          <div class="panel-header">
            <span class="panel-title">🎨 Background</span>
            <button class="icon-btn" title="Close" @click="panelOpen = false">✕</button>
          </div>

          <!-- Preset gradients -->
          <div class="section-label">Presets</div>
          <div class="presets">
            <button
              v-for="(grad, key) in GRADIENTS"
              :key="key"
              class="chip"
              :class="{ active: preset === key }"
              :style="{ '--chip-bg': grad }"
              @click="preset = key; persist()"
            >{{ { 'violet-pink': 'Violet', 'blue-cyan': 'Blue', sunset: 'Sunset', forest: 'Forest', midnight: 'Night' }[key] }}</button>
          </div>

          <!-- Custom image -->
          <div class="section-label">Custom Image</div>
          <div class="custom-row">
            <button class="upload-btn" @click="triggerUpload">
              <span>⬆</span> Upload Image
            </button>
            <button
              v-if="customBg"
              class="remove-btn"
              title="Remove custom image"
              @click="removeCustomBg"
            >✕ Remove</button>
          </div>
          <div v-if="customBg" class="preview-wrap">
            <img :src="customBg" class="preview-img" alt="Custom background preview" />
            <span class="preview-badge" :class="{ active: preset === 'custom' }">
              {{ preset === 'custom' ? '✓ Active' : 'Not active' }}
            </span>
            <button
              v-if="preset !== 'custom'"
              class="apply-btn"
              @click="preset = 'custom'; persist()"
            >Apply</button>
          </div>

          <!-- Controls -->
          <div class="section-label">Options</div>
          <label class="chk-row">
            <input type="checkbox" v-model="blur" @change="persist" class="chk" />
            <span>Blur background</span>
          </label>

          <div class="slider-row">
            <span class="slider-label">Dim</span>
            <input
              class="range"
              type="range"
              min="0" max="0.75" step="0.05"
              v-model.number="dim"
              @change="persist"
            />
            <span class="slider-val">{{ Math.round(dim * 100) }}%</span>
          </div>

          <button class="reset-btn" @click="resetTheme">↺ Reset to default</button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr;
  position: relative;
}

/* ── Background layers ── */
.bg {
  position: fixed;
  inset: 0;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  z-index: -2;
  transition: filter 200ms ease;
}
.bg-overlay {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  transition: background 200ms ease;
}

/* ── Header ── */
.header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: transparent;
}
.head {
  max-width: var(--container-w);
  margin: 0 auto;
  padding: var(--space-4) var(--space-6);
  display: grid;
  place-items: center;
}
.head-card {
  width: 100%;
  max-width: 720px;
  box-sizing: border-box;
  padding: var(--space-3) var(--space-5);
  border-radius: 999px;
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 75%, transparent);
  backdrop-filter: saturate(1.1) blur(8px);
  box-shadow: var(--shadow-1);
  display: grid;
  place-items: center;
}
.brand {
  font-weight: 700;
  text-align: center;
}

/* ── Main slot ── */
.main {
  display: grid;
  min-height: calc(100vh - 72px);
  place-items: center;
  padding: var(--space-6);
}

/* ── FAB ── */
.fab-wrap {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 50;
}
.fab {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  border: 1px solid color-mix(in oklab, var(--border) 70%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 80%, transparent);
  backdrop-filter: saturate(1.2) blur(10px);
  box-shadow: var(--shadow-1);
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--text);
  transition: box-shadow 0.2s, background 0.2s;
}
.fab:hover,
.fab.active {
  background: color-mix(in oklab, var(--bg-elev) 95%, transparent);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--brand) 25%, transparent), var(--shadow-1);
}
.fab-icon {
  width: 20px;
  height: 20px;
  display: block;
}

/* ── Panel transition ── */
.panel-enter-active,
.panel-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.97);
}

/* ── Panel ── */
.panel {
  position: absolute;
  right: 0;
  bottom: 58px;
  width: min(320px, calc(100vw - 32px));
  box-sizing: border-box;
  padding: var(--space-4);
  background: color-mix(in oklab, var(--bg-elev) 90%, transparent);
  backdrop-filter: saturate(1.2) blur(14px);
  border: 1px solid color-mix(in oklab, var(--border) 70%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0,0,0,0.18), var(--shadow-1);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-weight: 700;
  font-size: 0.95rem;
}
.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in oklab, var(--border) 70%, transparent);
  background: transparent;
  font-size: 0.8rem;
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--text);
  opacity: 0.7;
  transition: opacity 0.15s;
}
.icon-btn:hover {
  opacity: 1;
  border-color: var(--border);
}

/* ── Section label ── */
.section-label {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  opacity: 0.55;
  margin-top: var(--space-1);
}

/* ── Presets ── */
.presets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.chip {
  flex: 1 1 auto;
  min-width: 52px;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  padding: 7px 10px;
  cursor: pointer;
  position: relative;
  font-size: 0.82rem;
  font-weight: 500;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0,0,0,0.4);
  overflow: hidden;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chip::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--chip-bg, #888);
  z-index: -1;
}
.chip.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--brand);
}

/* ── Custom image ── */
.custom-row {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.upload-btn {
  flex: 1 1 auto;
  height: 36px;
  border-radius: var(--radius-sm);
  border: 1px dashed color-mix(in oklab, var(--border) 90%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 60%, transparent);
  color: var(--text);
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: border-color 0.15s, background 0.15s;
}
.upload-btn:hover {
  border-color: var(--brand);
  background: color-mix(in oklab, var(--brand) 8%, transparent);
}
.remove-btn {
  height: 36px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(196, 49, 49, 0.35);
  background: transparent;
  color: #e05252;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.15s;
}
.remove-btn:hover {
  background: rgba(196, 49, 49, 0.1);
}

.preview-wrap {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
}
.preview-img {
  width: 100%;
  height: 80px;
  object-fit: cover;
  display: block;
}
.preview-badge {
  position: absolute;
  top: 6px;
  left: 8px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.55);
  color: rgba(255,255,255,0.75);
}
.preview-badge.active {
  background: rgba(27, 156, 63, 0.85);
  color: #fff;
}
.apply-btn {
  position: absolute;
  top: 6px;
  right: 8px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  border: none;
  background: var(--brand);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}
.apply-btn:hover {
  background: var(--brand-600);
}

/* ── Controls ── */
.chk-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.9rem;
  cursor: pointer;
  user-select: none;
}
.chk {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--brand);
}

.slider-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.9rem;
}
.slider-label {
  min-width: 28px;
}
.range {
  flex: 1;
  accent-color: var(--brand);
}
.slider-val {
  min-width: 36px;
  text-align: right;
  font-size: 0.82rem;
  opacity: 0.7;
  font-variant-numeric: tabular-nums;
}

/* ── Reset ── */
.reset-btn {
  height: 34px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(182, 29, 29, 0.3);
  background: transparent;
  color: #b61d1d;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  width: 100%;
}
.reset-btn:hover {
  background: rgba(182, 29, 29, 0.08);
}
</style>
