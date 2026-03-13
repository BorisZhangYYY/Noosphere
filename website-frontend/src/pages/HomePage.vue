<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { logout } from '../services/auth.js'

const router = useRouter()
const SIDEBAR_EXPANDED_WIDTH = 208
const SIDEBAR_COLLAPSED_WIDTH = 72

const username = ref(localStorage.getItem('username') || 'User')
const sidebarWidth = ref(SIDEBAR_EXPANDED_WIDTH)
const profileModalVisible = ref(false)
const logoutLoading = ref(false)
const browsingHistory = ref([])
const accountCardRef = ref(null)
const sidePanelRef = ref(null)
const floatingPanelRef = ref(null)
const accountMenuOpen = ref(false)
const activePanel = ref('')
const centerMode = ref('explore')
const floatingPanelOpen = ref(false)
const floatingPanelKey = ref('')
const floatingPanelTop = ref(16)

const initials = computed(() => {
  const name = username.value || 'U'
  return name
    .split(/[\s_\-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
})

const navItems = [
  { key: 'publish', icon: '📝', label: 'Publish' },
  { key: 'draft', icon: '📦', label: 'Draft Box' },
  { key: 'bookmarks', icon: '🔖', label: 'Bookmarks' },
  { key: 'friends', icon: '👥', label: 'Friends' },
  { key: 'history', icon: '📋', label: 'History' },
]

const placeholderPosts = [
  {
    id: 1,
    title: 'Understanding Quantum Computing Basics',
    excerpt:
      'Quantum computers leverage the principles of superposition and entanglement to solve problems that are intractable for classical machines…',
    tag: 'Science',
    readTime: '5 min read',
  },
  {
    id: 2,
    title: 'The Art of Writing Clean Code',
    excerpt:
      'Clean code is not just about style — it communicates intent, reduces bugs, and makes future changes easier for every engineer on the team…',
    tag: 'Engineering',
    readTime: '4 min read',
  },
  {
    id: 3,
    title: 'Why Sleep Is Your Superpower',
    excerpt:
      'Modern neuroscience confirms what our grandmothers always knew: consistent, quality sleep is the single highest-leverage investment in cognitive performance…',
    tag: 'Health',
    readTime: '3 min read',
  },
]

const historyExamples = [
  { id: 'example-1', type: 'Science', title: 'Understanding Quantum Computing Basics' },
  { id: 'example-2', type: 'Engineering', title: 'The Art of Writing Clean Code' },
  { id: 'example-3', type: 'Health', title: 'Why Sleep Is Your Superpower' },
]

const draftExamples = [
  { id: 'draft-1', type: 'Draft', title: 'Async API design checklist' },
  { id: 'draft-2', type: 'Draft', title: 'Database migration rollback notes' },
]

const bookmarkExamples = [
  { id: 'bookmark-1', type: 'Bookmark', title: 'Vue composables patterns' },
  { id: 'bookmark-2', type: 'Bookmark', title: 'Flask auth middleware flow' },
]

const friendExamples = [
  { id: 'friend-1', type: 'Friend', title: 'Alice · Shared: Clean architecture notes' },
  { id: 'friend-2', type: 'Friend', title: 'Bob · Shared: CSS motion references' },
]

const isIconMode = computed(() => sidebarWidth.value <= 132)
const homeStyle = computed(() => ({ '--sidebar-w': `${sidebarWidth.value}px` }))
const showAccountActions = computed(() => accountMenuOpen.value && !isIconMode.value)
const panelViewKey = computed(() => (isIconMode.value ? floatingPanelKey.value : activePanel.value))
const showFloatingPanel = computed(() => isIconMode.value && floatingPanelOpen.value && !!floatingPanelKey.value)
const floatingPanelStyle = computed(() => ({
  left: `${sidebarWidth.value + 12}px`,
  top: `${floatingPanelTop.value}px`,
}))
const historyDisplayItems = computed(() => {
  if (browsingHistory.value.length > 0) {
    return browsingHistory.value.map((item) => ({
      id: item.id,
      type: item.type || 'Article',
      title: item.title,
    }))
  }
  return historyExamples
})
const activePanelLabel = computed(() => {
  const found = navItems.find((item) => item.key === panelViewKey.value)
  return found ? found.label : ''
})
const activePanelIcon = computed(() => {
  const found = navItems.find((item) => item.key === panelViewKey.value)
  return found ? found.icon : ''
})
const activePanelItems = computed(() => {
  if (panelViewKey.value === 'history') {
    return historyDisplayItems.value
  }
  if (panelViewKey.value === 'draft') {
    return draftExamples
  }
  if (panelViewKey.value === 'bookmarks') {
    return bookmarkExamples
  }
  if (panelViewKey.value === 'friends') {
    return friendExamples
  }
  return []
})

function showProfileSettings() {
  profileModalVisible.value = true
}

function closeProfileModal() {
  profileModalVisible.value = false
}

function toggleAccountMenu() {
  if (isIconMode.value) {
    accountMenuOpen.value = false
    return
  }
  accountMenuOpen.value = !accountMenuOpen.value
}

function toggleSidebarMode() {
  if (isIconMode.value) {
    sidebarWidth.value = SIDEBAR_EXPANDED_WIDTH
    floatingPanelOpen.value = false
    floatingPanelKey.value = ''
    localStorage.setItem('hk_sidebar_collapsed', '0')
    return
  }
  sidebarWidth.value = SIDEBAR_COLLAPSED_WIDTH
  activePanel.value = ''
  accountMenuOpen.value = false
  localStorage.setItem('hk_sidebar_collapsed', '1')
}

function onClickNav(item, event) {
  if (item.key === 'publish') {
    centerMode.value = 'publish'
    activePanel.value = ''
    floatingPanelOpen.value = false
    floatingPanelKey.value = ''
    return
  }

  centerMode.value = 'explore'
  if (isIconMode.value) {
    if (event?.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect()
      floatingPanelTop.value = Math.max(10, Math.min(window.innerHeight - 360, rect.top - 10))
    }
    if (floatingPanelOpen.value && floatingPanelKey.value === item.key) {
      floatingPanelOpen.value = false
      floatingPanelKey.value = ''
    } else {
      floatingPanelOpen.value = true
      floatingPanelKey.value = item.key
    }
    activePanel.value = ''
  } else {
    activePanel.value = item.key
    floatingPanelOpen.value = false
    floatingPanelKey.value = ''
  }
  accountMenuOpen.value = false
}

function returnToDefaultNav() {
  activePanel.value = ''
  floatingPanelOpen.value = false
  floatingPanelKey.value = ''
}

function openHistoryRecord(item) {
  console.log('TODO: open history record', item.id)
}

function onOpenPost(post) {
  const nextItem = {
    id: Date.now(),
    type: post.tag,
    title: post.title,
    at: new Date().toLocaleString(),
  }
  browsingHistory.value = [nextItem, ...browsingHistory.value].slice(0, 8)
  localStorage.setItem('hk_browsing_history', JSON.stringify(browsingHistory.value))
}

function closeAccountMenu() {
  accountMenuOpen.value = false
}

function onDocumentPointerDown(event) {
  const accountNode = accountCardRef.value
  const floatingNode = floatingPanelRef.value
  const clickedInsideFloating = Boolean(floatingNode && floatingNode.contains(event.target))
  const clickedInsideAccount = Boolean(accountNode && accountNode.contains(event.target))

  if (!clickedInsideFloating) {
    floatingPanelOpen.value = false
    floatingPanelKey.value = ''
  }
  if (!clickedInsideAccount) {
    closeAccountMenu()
  }
}

async function onLogout() {
  if (logoutLoading.value) return
  logoutLoading.value = true
  try {
    const token = localStorage.getItem('access_token') || ''
    await logout(token)
  } catch (error) {
    console.warn('Logout request failed:', error)
  } finally {
    localStorage.removeItem('access_token')
    localStorage.removeItem('username')
    logoutLoading.value = false
    router.push('/login')
  }
}

onMounted(() => {
  const collapsedState = localStorage.getItem('hk_sidebar_collapsed')
  if (collapsedState === '1') {
    sidebarWidth.value = SIDEBAR_COLLAPSED_WIDTH
  } else {
    sidebarWidth.value = SIDEBAR_EXPANDED_WIDTH
  }

  const savedHistory = localStorage.getItem('hk_browsing_history')
  if (savedHistory) {
    try {
      const parsed = JSON.parse(savedHistory)
      browsingHistory.value = Array.isArray(parsed) ? parsed : []
    } catch {
      browsingHistory.value = []
    }
  }

  window.addEventListener('mousedown', onDocumentPointerDown)
  window.addEventListener('touchstart', onDocumentPointerDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousedown', onDocumentPointerDown)
  window.removeEventListener('touchstart', onDocumentPointerDown)
})
</script>

<template>
  <div class="home-root" :class="{ 'icon-mode': isIconMode }" :style="homeStyle">
    <aside ref="sidePanelRef" class="side-panel">
      <div class="brand-header">
        <div class="brand-block">
          <span class="brand-mark">🌍</span>
          <span v-if="!isIconMode" class="brand-text">Noosphere</span>
        </div>
        <button class="collapse-btn" @click="toggleSidebarMode">
          <span class="collapse-icon">{{ isIconMode ? '⟩' : '⟨' }}</span>
        </button>
      </div>
      <div class="section-divider"></div>

      <div class="side-main">
        <Transition name="panel-switch" mode="out-in">
          <div v-if="activePanel && !isIconMode" key="panel" class="panel-content">
            <div class="panel-head">
              <div class="panel-head-main">
                <span class="nav-icon">{{ activePanelIcon }}</span>
                <span class="panel-title">{{ activePanelLabel }}</span>
              </div>
              <button class="panel-return" @click="returnToDefaultNav">Return</button>
            </div>
            <div class="section-divider panel-divider"></div>
            <div class="history-frame">
              <div class="history-list">
                <button
                  v-for="item in activePanelItems"
                  :key="item.id"
                  class="history-item"
                  @click="openHistoryRecord(item)"
                >
                  <span class="history-item-type">{{ item.type }}</span>
                  <span class="history-item-title">{{ item.title }}</span>
                </button>
              </div>
              <p class="history-hint">Future: click item to jump to article page</p>
            </div>
          </div>

          <div v-else key="nav" class="nav-content">
            <nav class="nav-list">
              <button
                v-for="item in navItems"
                :key="item.key"
                class="nav-item"
                @click="onClickNav(item, $event)"
              >
                <span class="nav-icon">{{ item.icon }}</span>
                <span v-if="!isIconMode" class="nav-label">{{ item.label }}</span>
              </button>
            </nav>
          </div>
        </Transition>
      </div>

      <section ref="accountCardRef" class="account-card" :class="{ open: showAccountActions }">
        <button class="account-head" @click.stop="toggleAccountMenu">
          <div class="avatar">{{ initials }}</div>
          <div v-if="!isIconMode" class="account-meta">
            <div class="account-name">{{ username }}</div>
            <div class="account-role">Member</div>
          </div>
        </button>
        <div v-if="showAccountActions" class="account-menu">
          <button
            class="account-action"
            @click="returnToDefaultNav"
          >
            <span class="nav-icon">👤</span>
            <span class="nav-label">My Profile</span>
          </button>
          <button class="account-action" @click="showProfileSettings">
            <span class="nav-icon">⚙️</span>
            <span class="nav-label">Settings</span>
          </button>
          <button class="account-action danger" :disabled="logoutLoading" @click="onLogout">
            <span class="nav-icon">🚪</span>
            <span class="nav-label">{{ logoutLoading ? 'Logging out…' : 'Logout' }}</span>
          </button>
        </div>
      </section>
    </aside>

    <main class="center-col">
      <section v-if="centerMode === 'publish'" class="center-shell">
        <div class="feed-toolbar">
          <div class="toolbar-title-wrap">
            <h2 class="feed-title">Publish</h2>
            <p class="feed-sub">Writing workspace placeholder</p>
          </div>
        </div>
        <div class="publish-placeholder">
          <h3 class="publish-title">New Article Draft</h3>
          <p class="publish-copy">Editor feature will be implemented in the next step.</p>
          <button class="publish-disabled-btn" disabled>Start Writing</button>
        </div>
      </section>

      <section v-else class="center-shell">
        <div class="feed-toolbar">
          <div class="toolbar-title-wrap">
            <h2 class="feed-title">Explore</h2>
            <p class="feed-sub">Hot knowledge and engineering insights</p>
          </div>
          <div class="search-bar">
            <span class="search-icon">🔍</span>
            <input
              class="search-input"
              type="text"
              placeholder="Search topics"
              disabled
            />
          </div>
        </div>
        <div class="feed-list">
          <article v-for="post in placeholderPosts" :key="post.id" class="post-card">
            <div class="post-meta">
              <span class="post-tag">{{ post.tag }}</span>
              <span class="post-read-time">{{ post.readTime }}</span>
            </div>
            <h3 class="post-title">{{ post.title }}</h3>
            <p class="post-excerpt">{{ post.excerpt }}</p>
            <button
              class="read-more"
              @click="onOpenPost(post)"
            >
              Read more →
            </button>
          </article>
        </div>
      </section>
    </main>

    <Teleport to="body">
      <Transition name="panel-slide">
        <section
          v-if="showFloatingPanel"
          ref="floatingPanelRef"
          class="floating-panel"
          :style="floatingPanelStyle"
        >
          <div class="panel-head">
            <div class="panel-head-main">
              <span class="nav-icon">{{ activePanelIcon }}</span>
              <span class="panel-title">{{ activePanelLabel }}</span>
            </div>
            <button class="panel-return" @click="returnToDefaultNav">Return</button>
          </div>
          <div class="section-divider panel-divider"></div>
          <div class="history-frame">
            <div class="history-list">
              <button
                v-for="item in activePanelItems"
                :key="item.id"
                class="history-item"
                @click="openHistoryRecord(item)"
              >
                <span class="history-item-type">{{ item.type }}</span>
                <span class="history-item-title">{{ item.title }}</span>
              </button>
            </div>
            <p class="history-hint">Future: click item to jump to article page</p>
          </div>
        </section>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <div v-if="profileModalVisible" class="modal-backdrop" @click.self="closeProfileModal">
        <div class="modal-box">
          <div class="modal-header">
            <span class="modal-title">Profile Settings</span>
            <button class="modal-close" @click="closeProfileModal">✕</button>
          </div>
          <div class="modal-body">
            <p class="coming-soon-text">🚧 Coming soon</p>
            <p class="coming-soon-hint">Profile customisation will be available in a future update.</p>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="closeProfileModal">Close</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.home-root {
  position: relative;
  isolation: isolate;
  width: 100%;
  height: 100dvh;
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  gap: 0;
  background: color-mix(in oklab, var(--bg) 32%, transparent);
  overflow: hidden;
}

.home-root::before {
  content: '';
  position: absolute;
  inset: -12px;
  background-image: var(--noosphere-pattern);
  background-size: 1200px 1200px;
  background-repeat: repeat;
  background-position: center;
  filter: blur(14px) saturate(1.1);
  opacity: 0.42;
  pointer-events: none;
  z-index: 0;
}

.side-panel {
  position: relative;
  z-index: 1;
  background: color-mix(in oklab, var(--bg) 62%, transparent);
  backdrop-filter: saturate(1.08) blur(7px);
  border-right: 1px solid color-mix(in oklab, var(--border) 88%, transparent);
  padding: 0.55rem 0.45rem calc(1.55rem + env(safe-area-inset-bottom));
  height: 100dvh;
  box-sizing: border-box;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 0.2rem;
}

.home-root.icon-mode .side-panel {
  padding-left: 0.16rem;
  padding-right: 0.16rem;
}

.brand-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 30px;
}

.collapse-btn {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  border: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 86%, transparent);
  color: var(--text);
  font-size: 0.86rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 0.12rem;
  flex-shrink: 0;
}

.collapse-btn:hover {
  border-color: color-mix(in oklab, var(--brand) 30%, transparent);
  background: color-mix(in oklab, var(--brand) 10%, var(--bg-elev));
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 0.42rem;
  min-height: 30px;
  padding: 0 0.38rem;
}

.home-root.icon-mode .brand-header {
  justify-content: center;
}

.home-root.icon-mode .brand-block {
  visibility: hidden;
  width: 0;
  min-width: 0;
  padding: 0;
}

.home-root.icon-mode .collapse-btn {
  position: static;
  margin: 0 auto;
}

.collapse-icon {
  transform: translateY(-1px);
}

.section-divider {
  height: 1px;
  margin: 0.1rem 0.2rem 0.18rem;
  background: linear-gradient(
    90deg,
    transparent 0%,
    color-mix(in oklab, var(--border) 94%, transparent) 18%,
    color-mix(in oklab, var(--border) 94%, transparent) 82%,
    transparent 100%
  );
}

.brand-mark {
  color: var(--brand);
  font-size: 0.78rem;
}

.brand-text {
  font-size: 0.83rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.nav-item,
.account-action {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.42rem;
  min-height: 30px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  padding: 0.34rem 0.4rem;
  text-align: left;
  cursor: pointer;
  font-size: 0.79rem;
}

.nav-item:hover,
.account-action:hover:not(:disabled) {
  background: color-mix(in oklab, var(--brand) 9%, transparent);
  border-color: color-mix(in oklab, var(--brand) 26%, transparent);
}

.home-root.icon-mode .nav-item,
.home-root.icon-mode .account-action {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
  min-height: 28px;
}

.nav-icon {
  min-width: 16px;
  width: 16px;
  font-size: 0.87rem;
  line-height: 1;
  text-align: center;
}

.home-root.icon-mode .nav-icon {
  min-width: 14px;
  width: 14px;
  font-size: 0.8rem;
}

.nav-label {
  line-height: 1.14;
  font-weight: 500;
}

.side-main {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 0.28rem;
}

.nav-content,
.panel-content {
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.14rem;
}

.history-frame {
  border: 1px solid color-mix(in oklab, var(--border) 82%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 60%, transparent);
  border-radius: 9px;
  padding: 0.28rem;
  backdrop-filter: saturate(1.08) blur(6px);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.26rem;
}

.panel-head-main {
  display: flex;
  align-items: center;
  gap: 0.32rem;
}

.panel-title {
  font-size: 0.79rem;
  font-weight: 700;
}

.panel-return {
  border: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 92%, transparent);
  border-radius: 999px;
  padding: 0.18rem 0.54rem;
  font-size: 0.67rem;
  cursor: pointer;
}

.panel-return:hover {
  border-color: color-mix(in oklab, var(--brand) 30%, transparent);
}

.panel-divider {
  margin-top: 0;
}

.history-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  column-gap: 0.3rem;
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  text-align: left;
  padding: 0.3rem 0.32rem;
  cursor: pointer;
}

.history-item:hover {
  background: color-mix(in oklab, var(--brand) 7%, transparent);
  border-color: color-mix(in oklab, var(--brand) 24%, transparent);
}

.history-item-title {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.2;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-item-type {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in oklab, var(--brand) 30%, transparent);
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 0.64rem;
  line-height: 1.2;
  color: var(--brand);
  background: color-mix(in oklab, var(--brand) 10%, transparent);
}

.history-hint {
  margin: 0.24rem 0 0;
  font-size: 0.67rem;
  opacity: 0.58;
  padding: 0 0.14rem;
}

.account-card {
  display: block;
  position: relative;
  border: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 60%, transparent);
  border-radius: 10px;
  padding: 0.34rem;
  overflow: visible;
  margin-top: 0;
  margin-bottom: 0.12rem;
}

.home-root.icon-mode .account-head {
  pointer-events: none;
  justify-content: center;
  width: 32px;
  min-height: 32px;
  padding: 0;
  margin: 0 auto;
}

.home-root.icon-mode .account-card {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  padding: 0.2rem;
  margin: 0 auto 0.12rem;
  border-radius: 999px;
}

.home-root.icon-mode .account-head .avatar {
  margin: 0 auto;
}

.account-card.open {
  border-color: color-mix(in oklab, var(--brand) 30%, var(--border));
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.1);
}

.account-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.42rem;
  padding: 0.22rem 0.16rem;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  min-height: 34px;
}

.account-head:hover {
  background: color-mix(in oklab, var(--brand) 8%, transparent);
  border-color: color-mix(in oklab, var(--brand) 24%, transparent);
}

.avatar {
  width: 26px;
  height: 26px;
  min-width: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--brand) 0%, #8a77f8 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.68rem;
  font-weight: 800;
}

.account-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.account-name {
  font-size: 0.79rem;
  font-weight: 700;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-role {
  font-size: 0.67rem;
  opacity: 0.58;
}

.account-menu {
  position: absolute;
  left: 0.34rem;
  right: 0.34rem;
  bottom: calc(100% + 0.22rem);
  width: auto;
  display: flex;
  flex-direction: column;
  gap: 0.14rem;
  border: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 72%, transparent);
  border-radius: 10px;
  padding: 0.26rem;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
  z-index: 12;
  backdrop-filter: saturate(1.08) blur(8px);
}

.floating-panel {
  position: fixed;
  width: min(300px, calc(100vw - 1.4rem));
  max-height: calc(100vh - 1.44rem);
  overflow-y: auto;
  border: 1px solid color-mix(in oklab, var(--border) 86%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 70%, transparent);
  border-radius: 12px;
  padding: 0.42rem;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.2);
  z-index: 40;
  backdrop-filter: saturate(1.1) blur(10px);
}

.account-action.danger {
  color: #b83939;
}

.account-action.danger:hover:not(:disabled) {
  background: color-mix(in oklab, rgba(184, 57, 57, 0.14) 84%, transparent);
  border-color: rgba(184, 57, 57, 0.3);
}

.account-action:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.center-col {
  position: relative;
  z-index: 1;
  min-width: 0;
  height: 100vh;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.center-shell {
  min-height: 100%;
  padding: 0.82rem 1.02rem;
}

.publish-placeholder {
  border: 1px dashed color-mix(in oklab, var(--border) 90%, transparent);
  border-radius: 12px;
  padding: 1rem;
  background: color-mix(in oklab, var(--bg-elev) 58%, transparent);
  display: flex;
  flex-direction: column;
  gap: 0.46rem;
  backdrop-filter: saturate(1.06) blur(7px);
}

.publish-title {
  margin: 0;
  font-size: 1rem;
}

.publish-copy {
  margin: 0;
  opacity: 0.66;
  font-size: 0.84rem;
}

.publish-disabled-btn {
  align-self: flex-start;
  border: 1px solid color-mix(in oklab, var(--brand) 30%, transparent);
  border-radius: 8px;
  padding: 0.4rem 0.76rem;
  background: color-mix(in oklab, var(--brand) 8%, transparent);
  color: var(--brand);
  font-weight: 600;
  opacity: 0.7;
}

.panel-switch-enter-active,
.panel-switch-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.panel-switch-enter-from,
.panel-switch-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(-18px) scale(0.98);
}

.feed-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.7rem;
  padding-bottom: 0.66rem;
  border-bottom: 1px solid color-mix(in oklab, var(--border) 82%, transparent);
  margin-bottom: 0.66rem;
}

.toolbar-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.feed-title {
  margin: 0;
  font-size: 1.02rem;
  font-weight: 700;
}

.feed-sub {
  margin: 0;
  font-size: 0.75rem;
  opacity: 0.62;
}

.search-bar {
  min-width: 200px;
  height: 34px;
  display: flex;
  align-items: center;
  gap: 0.42rem;
  border-radius: 999px;
  border: 1px solid color-mix(in oklab, var(--border) 84%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 88%, transparent);
  padding: 0 10px;
}

.search-icon {
  font-size: 0.82rem;
  opacity: 0.56;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 0.83rem;
  font-family: inherit;
  opacity: 0.65;
}

.feed-list {
  display: flex;
  flex-direction: column;
  gap: 0.54rem;
}

.post-card {
  background: color-mix(in oklab, var(--bg-elev) 62%, transparent);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: 11px;
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
  backdrop-filter: saturate(1.08) blur(8px);
}

.post-card:hover {
  background: color-mix(in oklab, var(--brand) 5%, var(--bg-elev));
  border-color: color-mix(in oklab, var(--brand) 34%, transparent);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}

.post-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.post-tag {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in oklab, var(--brand) 14%, transparent);
  border: 1px solid color-mix(in oklab, var(--brand) 28%, transparent);
  color: var(--brand);
}

.post-read-time {
  font-size: 0.74rem;
  opacity: 0.56;
}

.post-title {
  margin: 0;
  font-size: 0.97rem;
  font-weight: 700;
  line-height: 1.38;
}

.post-excerpt {
  margin: 0;
  font-size: 0.83rem;
  line-height: 1.58;
  opacity: 0.84;
}

.read-more {
  align-self: flex-start;
  padding: 0.34rem 0.78rem;
  border-radius: 8px;
  border: 1px solid color-mix(in oklab, var(--brand) 32%, transparent);
  background: transparent;
  color: var(--brand);
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
}

.read-more:hover {
  background: color-mix(in oklab, var(--brand) 11%, transparent);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.modal-box {
  background: color-mix(in oklab, var(--bg-elev) 92%, transparent);
  backdrop-filter: saturate(1.1) blur(16px);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.25);
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
}

.modal-title {
  font-weight: 700;
  font-size: 1rem;
}

.modal-close {
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  font-size: 0.85rem;
}

.modal-close:hover {
  opacity: 1;
  background: color-mix(in oklab, var(--bg-elev) 80%, transparent);
  border-color: var(--border);
}

.modal-body {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  text-align: center;
}

.coming-soon-text {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.coming-soon-hint {
  margin: 0;
  opacity: 0.65;
  font-size: 0.9rem;
}

.modal-footer {
  padding: var(--space-3) var(--space-5) var(--space-4);
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
}

.btn-secondary {
  padding: 0.55rem 1.2rem;
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 75%, transparent);
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
}

.btn-secondary:hover {
  border-color: var(--brand);
}

@media (max-width: 1219px) {
  .home-root {
    grid-template-columns: minmax(72px, var(--sidebar-w)) minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .home-root {
    grid-template-columns: max(72px, var(--sidebar-w)) minmax(0, 1fr);
  }

  .side-panel {
    padding-left: 0.24rem;
    padding-right: 0.24rem;
  }

  .feed-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-bar {
    min-width: 0;
    width: 100%;
  }

  .center-shell {
    padding: 0.66rem 0.7rem;
  }

  .post-card {
    padding: 0.68rem;
  }
}
</style>
