import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { layout: 'standalone' }
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('@/views/HomeView.vue'),
    meta: { layout: 'default', title: 'Workbench' }
  },
  {
    path: '/sc',
    name: 'sc-list',
    component: () => import('@/views/ScListView.vue'),
    meta: { layout: 'default', title: 'SC List' }
  },
  {
    path: '/sc/:id',
    name: 'sc-detail',
    component: () => import('@/views/ScDetailView.vue'),
    meta: { layout: 'default', title: 'SC Detail' }
  },
  {
    path: '/sc/:scId/po/:poId',
    name: 'po-detail',
    component: () => import('@/views/PoDetailView.vue'),
    meta: { layout: 'default', title: 'PO Detail' }
  },
  {
    path: '/po',
    name: 'po-list',
    component: () => import('@/views/PoListView.vue'),
    meta: { layout: 'default', title: 'PO List' }
  },
  {
    path: '/gr',
    name: 'gr-list',
    component: () => import('@/views/GrListView.vue'),
    meta: { layout: 'default', title: 'GR List' }
  },
  {
    path: '/vendor',
    name: 'vendor-list',
    component: () => import('@/views/VendorListView.vue'),
    meta: { layout: 'default', title: 'Vendor List' }
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { layout: 'default', title: 'Audit Logs' }
  },
  {
    path: '/system',
    name: 'system',
    component: () => import('@/views/SystemView.vue'),
    meta: { layout: 'default', title: 'System' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  if (to.name === 'login') return next()

  try {
    const { callApi } = await import('@/api/bridge.js')
    const user = await callApi('current_user')
    window.__currentUser = user
    next()
  } catch {
    next({ name: 'login', query: { redirect: to.fullPath } })
  }
})

export default router
