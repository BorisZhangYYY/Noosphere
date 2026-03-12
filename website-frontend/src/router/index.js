import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    redirect: "/login",
  },
  {
    path: "/login",
    name: "Login",
    component: () => import("../pages/LoginPage.vue"),
    meta: { guestOnly: true },
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("../pages/Register.vue"),
    meta: { guestOnly: true },
  },
  {
    path: "/forgot-password",
    name: "ForgotPassword",
    component: () => import("../pages/ForgotPasswordPage.vue"),
    meta: { guestOnly: true },
  },
  {
    path: "/home",
    name: "Home",
    component: () => import("../pages/HomePage.vue"),
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, _from, next) => {
  const isLoggedIn = !!localStorage.getItem("access_token");

  // Protected route — must be logged in
  if (to.meta.requiresAuth && !isLoggedIn) {
    return next("/login");
  }

  // Guest-only route — already logged in, send to home
  if (to.meta.guestOnly && isLoggedIn) {
    return next("/home");
  }

  next();
});

export default router;
