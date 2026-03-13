<template>
  <div class="shell">
    <main class="main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: block;
  position: relative;
  background: transparent;
}
.main {
  min-height: 100vh;
  padding: 0;
  position: relative;
  z-index: 1;
}
</style>
