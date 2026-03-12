<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { logout } from '../services/auth.js'

const router = useRouter()

const username = ref(localStorage.getItem('username') || 'User')
const sidebarOpen = ref(true)
const profileModalVisible = ref(false)
const logoutLoading = ref(false)

const initials = computed(() => {
  const name = username.value || 'U'
  return name
    .split(/[\s_\-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
})

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function showProfileSettings() {
  profileModalVisible.value = true
}

function closeProfileModal() {
  profileModalVisible.value = false
}

function handleNavClick(label) {
  console.log('TODO:', label)
}

async function onLogout() {
  if (logoutLoading.value) return
  logoutLoading.value = true
  try {
    const token = localStorage.getItem('access_token') || ''
    await logout(token)
  } catch (e) {
    console.warn('Logout request failed:', e)
  } finally {
    localStorage.removeItem('access_token')
    localStorage.removeItem('username')
    logoutLoading.value = false
    router.push('/login')
  }
}

const navItems = [
  { icon: '📝', label: 'Publish Content' },
  { icon: '📦', label: 'Draft Box' },
  { icon: '📋', label: 'History' },
  { icon: '👥', label: 'Friends' },
  { icon: '👤', label: 'My Profile' },
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

onMounted(() => {
  // On small screens default sidebar to closed
  if (window.innerWidth < 768) {
    sidebarOpen.value = false
  }
})
</script>

<template>
  <div class="home-root">
    <!-- ── Mobile hamburger ── -->
    <button
      class="hamburger"
      :class="{ open: sidebarOpen }"
      @click="toggleSidebar"
      :title="sidebarOpen ? 'Close sidebar' : 'Open sidebar'"
      aria-label="Toggle sidebar"
    >
      <span class="bar"></span>
      <span class="bar"></span>
      <span class="bar"></span>
    </button>

    <!-- ── Sidebar overlay (mobile) ── -->
    <div
      v-if="sidebarOpen"
      class="sidebar-overlay"
      @click="sidebarOpen = false"
    ></div>

    <!-- ── Left Sidebar ── -->
    <aside class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <!-- User info -->
      <div class="user-block">
        <div class="avatar">{{ initials }}</div>
        <div class="user-info">
          <div class="user-name">{{ username }}</div>
          <div class="user-role">Member</div>
        </div>
      </div>

      <div class="divider"></div>

      <!-- Nav items -->
      <nav class="nav-list">
        <button
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          @click="handleNavClick(item.label)"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </button>

        <button class="nav-item" @click="showProfileSettings">
          <span class="nav-icon">⚙️</span>
          <span class="nav-label">Profile Settings</span>
        </button>
      </nav>

      <div class="sidebar-spacer"></div>
      <div class="divider"></div>

      <!-- Logout -->
      <button
        class="logout-btn"
        :disabled="logoutLoading"
        @click="onLogout"
      >
        <span class="nav-icon">🚪</span>
        <span class="nav-label">{{ logoutLoading ? 'Logging out…' : 'Logout' }}</span>
      </button>
    </aside>

    <!-- ── Center column ── -->
    <div class="center-col">
      <!-- Search bar -->
      <div class="search-wrap">
        <div class="search-bar">
          <span class="search-icon">🔍</span>
          <input
            class="search-input"
            type="text"
            placeholder="Search hot topics…"
            disabled
          />
          <span class="search-todo">Coming soon</span>
        </div>
      </div>

      <!-- Feed header -->
      <div class="feed-header">
        <h2 class="feed-title">🔥 Hot Knowledge Feed</h2>
        <p class="feed-sub">Content coming soon in v0.6</p>
      </div>

      <!-- Placeholder post cards -->
      <div class="feed-list">
        <article
          v-for="post in placeholderPosts"
          :key="post.id"
          class="post-card"
        >
          <div class="post-meta">
            <span class="post-tag">{{ post.tag }}</span>
            <span class="post-read-time">{{ post.readTime }}</span>
          </div>
          <h3 class="post-title">{{ post.title }}</h3>
          <p class="post-excerpt">{{ post.excerpt }}</p>
          <button class="read-more" @click="console.log('TODO: open post', post.id)">
            Read more →
          </button>
        </article>
      </div>
    </div>

    <!-- ── Right bookmarks panel ── -->
    <aside class="right-panel">
      <div class="panel-card">
        <div class="panel-heading">
          <span class="panel-icon">🔖</span>
          <span>Bookmarks</span>
        </div>
        <div class="empty-state">
          <span class="empty-icon">📭</span>
          <p class="empty-text">No bookmarks yet</p>
          <p class="empty-hint">Save posts to read them later.</p>
        </div>
      </div>

      <div class="panel-card trending-card">
        <div class="panel-heading">
          <span class="panel-icon">📈</span>
          <span>Trending</span>
        </div>
        <div class="empty-state">
          <span class="empty-icon">🚧</span>
          <p class="empty-text">Coming soon</p>
        </div>
      </div>
    </aside>

    <!-- ── Profile settings modal ── -->
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
/* ────────────────────────────────────────
   Root grid
──────────────────────────────────────── */
.home-root {
  display: grid;
  grid-template-columns: 240px 1fr 260px;
  grid-template-areas: 'sidebar center right';
  gap: var(--space-4);
  align-items: start;
  width: 100%;
  max-width: var(--container-w);
  margin: 0 auto;
  min-height: calc(100vh - 80px);
  padding: var(--space-4) var(--space-4) var(--space-6);
  box-sizing: border-box;
  position: relative;
}

/* ────────────────────────────────────────
   Sidebar
──────────────────────────────────────── */
.sidebar {
  grid-area: sidebar;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: color-mix(in oklab, var(--bg-elev) 75%, transparent);
  backdrop-filter: saturate(1.1) blur(10px);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: var(--space-4) var(--space-3);
  position: sticky;
  top: calc(64px + var(--space-4));
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  box-sizing: border-box;
  transition: transform 0.25s ease, opacity 0.25s ease;
  min-height: 480px;
}

.user-block {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-2) var(--space-3);
}

.avatar {
  width: 44px;
  height: 44px;
  min-width: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--brand) 0%, #a4508b 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 0.95rem;
  color: #fff;
  letter-spacing: 0.02em;
  box-shadow: 0 2px 8px color-mix(in oklab, var(--brand) 35%, transparent);
  user-select: none;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.user-name {
  font-weight: 700;
  font-size: 0.95rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 0.78rem;
  opacity: 0.6;
}

.divider {
  height: 1px;
  background: color-mix(in oklab, var(--border) 80%, transparent);
  margin: var(--space-2) 0;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: 0.6rem var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
  transition: background 0.15s, border-color 0.15s;
}

.nav-item:hover {
  background: color-mix(in oklab, var(--brand) 10%, transparent);
  border-color: color-mix(in oklab, var(--brand) 25%, transparent);
}

.nav-icon {
  font-size: 1.05rem;
  width: 22px;
  text-align: center;
  flex-shrink: 0;
}

.nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-spacer {
  flex: 1;
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: 0.6rem var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-size: 0.9rem;
  font-weight: 500;
  color: #c43131;
  transition: background 0.15s, border-color 0.15s;
  margin-top: var(--space-2);
}

.logout-btn:hover:not(:disabled) {
  background: color-mix(in oklab, rgba(196, 49, 49, 0.15) 80%, transparent);
  border-color: rgba(196, 49, 49, 0.3);
}

.logout-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ────────────────────────────────────────
   Center column
──────────────────────────────────────── */
.center-col {
  grid-area: center;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

/* Search */
.search-wrap {
  position: sticky;
  top: calc(64px + var(--space-4));
  z-index: 5;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: color-mix(in oklab, var(--bg-elev) 80%, transparent);
  backdrop-filter: saturate(1.1) blur(10px);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: 999px;
  box-shadow: var(--shadow-1);
  padding: 0 var(--space-4);
  height: 48px;
}

.search-icon {
  font-size: 1rem;
  opacity: 0.7;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-size: 0.95rem;
  font-family: inherit;
  cursor: not-allowed;
  opacity: 0.6;
}

.search-todo {
  font-size: 0.75rem;
  opacity: 0.5;
  white-space: nowrap;
  background: color-mix(in oklab, var(--bg-elev) 70%, transparent);
  border: 1px solid color-mix(in oklab, var(--border) 60%, transparent);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
}

/* Feed header */
.feed-header {
  text-align: center;
  padding: var(--space-3) 0 var(--space-2);
}

.feed-title {
  margin: 0 0 var(--space-2);
  font-size: 1.6rem;
}

.feed-sub {
  margin: 0;
  opacity: 0.6;
  font-size: 0.9rem;
}

/* Post cards */
.feed-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.post-card {
  background: color-mix(in oklab, var(--bg-elev) 78%, transparent);
  backdrop-filter: saturate(1.1) blur(8px);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition: border-color 0.2s;
}

.post-card:hover {
  border-color: color-mix(in oklab, var(--brand) 40%, transparent);
}

.post-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.post-tag {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  background: color-mix(in oklab, var(--brand) 15%, transparent);
  border: 1px solid color-mix(in oklab, var(--brand) 30%, transparent);
  color: var(--brand);
}

.post-read-time {
  font-size: 0.8rem;
  opacity: 0.55;
}

.post-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1.35;
}

.post-excerpt {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.65;
  opacity: 0.8;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.read-more {
  align-self: flex-start;
  background: none;
  border: 1px solid color-mix(in oklab, var(--brand) 35%, transparent);
  border-radius: var(--radius-sm);
  color: var(--brand);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.4rem 0.9rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.read-more:hover {
  background: color-mix(in oklab, var(--brand) 12%, transparent);
  border-color: var(--brand);
}

/* ────────────────────────────────────────
   Right panel
──────────────────────────────────────── */
.right-panel {
  grid-area: right;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  position: sticky;
  top: calc(64px + var(--space-4));
}

.panel-card {
  background: color-mix(in oklab, var(--bg-elev) 75%, transparent);
  backdrop-filter: saturate(1.1) blur(10px);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.panel-heading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 700;
  font-size: 0.95rem;
}

.panel-icon {
  font-size: 1rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  text-align: center;
}

.empty-icon {
  font-size: 2rem;
  line-height: 1;
}

.empty-text {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 600;
  opacity: 0.75;
}

.empty-hint {
  margin: 0;
  font-size: 0.8rem;
  opacity: 0.55;
}

/* ────────────────────────────────────────
   Hamburger (mobile only)
──────────────────────────────────────── */
.hamburger {
  display: none;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 5px;
  width: 40px;
  height: 40px;
  padding: 0;
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  background: color-mix(in oklab, var(--bg-elev) 75%, transparent);
  backdrop-filter: blur(6px);
  position: fixed;
  bottom: 72px;
  left: 16px;
  z-index: 30;
  cursor: pointer;
  box-shadow: var(--shadow-1);
}

.bar {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text);
  border-radius: 2px;
  transition: transform 0.2s, opacity 0.2s;
}

.sidebar-overlay {
  display: none;
}

/* ────────────────────────────────────────
   Profile settings modal
──────────────────────────────────────── */
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
  line-height: 1;
}

.modal-close:hover {
  opacity: 1;
  background: color-mix(in oklab, var(--bg-elev) 80%, transparent);
  border-color: var(--border);
}

.modal-body {
  padding: var(--space-5);
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

/* ────────────────────────────────────────
   Responsive
──────────────────────────────────────── */
@media (max-width: 1024px) {
  .home-root {
    grid-template-columns: 220px 1fr;
    grid-template-areas:
      'sidebar center'
      'sidebar right';
  }

  .right-panel {
    grid-area: right;
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .panel-card {
    flex: 1;
    min-width: 200px;
  }
}

@media (max-width: 768px) {
  .home-root {
    grid-template-columns: 1fr;
    grid-template-areas:
      'center'
      'right';
    padding: var(--space-3);
    gap: var(--space-3);
  }

  .hamburger {
    display: flex;
  }

  .sidebar {
    grid-area: unset;
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    max-height: 100vh;
    z-index: 40;
    border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
    transform: translateX(0);
    transition: transform 0.25s ease;
    overflow-y: auto;
  }

  .sidebar.collapsed {
    transform: translateX(-100%);
  }

  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 39;
    backdrop-filter: blur(2px);
  }

  .search-wrap {
    top: var(--space-3);
  }

  .right-panel {
    grid-area: right;
    flex-direction: column;
    position: static;
  }

  .panel-card {
    min-width: unset;
  }
}
</style>
