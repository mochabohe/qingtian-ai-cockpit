import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('@/views/Home.vue') },
  { path: '/upload', name: 'upload', component: () => import('@/views/DataUpload.vue') },
  { path: '/dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
  { path: '/agent', name: 'agent', component: () => import('@/views/AgentConsole.vue') },
  { path: '/opportunity', name: 'opportunity', component: () => import('@/views/OpportunityMap.vue') },
  { path: '/report', name: 'report', component: () => import('@/views/ReportPreview.vue') },
  { path: '/video', name: 'video', component: () => import('@/views/VideoStudio.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
