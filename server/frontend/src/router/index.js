import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: () => import('../layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览' } },
      { path: 'key', name: 'key', component: () => import('../views/Key.vue'), meta: { title: '密钥管理' } },
      { path: 'logs', name: 'logs', component: () => import('../views/Logs.vue'), meta: { title: '日志查看' } },
      { path: 'bans', name: 'bans', component: () => import('../views/Bans.vue'), meta: { title: '封禁管理' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    return { path: '/login' }
  }
  if (to.path === '/login' && token) {
    return { path: '/' }
  }
  return true
})

export default router
