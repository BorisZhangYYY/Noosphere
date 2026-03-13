<template>
  <div class="card">
    <slot />
  </div>
</template>

<style scoped>
.card {
  background: var(--bg-elev);
  border: 1px solid color-mix(in oklab, var(--border) 80%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: var(--space-6);
  width: 100%;
  max-width: 720px;
  box-sizing: border-box;
}
</style>
