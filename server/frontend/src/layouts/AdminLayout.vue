<template>
  <el-container class="layout">
    <el-aside width="200px">
      <div class="logo">数图预约后台</div>
      <el-menu :default-active="$route.path" router background-color="#1f2d3d" text-color="#c0c4cc" active-text-color="#409eff">
        <el-menu-item index="/dashboard">总览</el-menu-item>
        <el-menu-item index="/key">密钥管理</el-menu-item>
        <el-menu-item index="/logs">日志查看</el-menu-item>
        <el-menu-item index="/bans">封禁管理</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="title">{{ $route.meta.title }}</span>
        <span class="right">
          <span class="user">{{ auth.username }}</span>
          <el-button link type="danger" @click="logout">退出</el-button>
        </span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.logo {
  height: 56px;
  line-height: 56px;
  text-align: center;
  color: #fff;
  font-weight: 600;
  background: #1f2d3d;
}
.el-aside {
  background: #1f2d3d;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
}
.header .title {
  font-size: 16px;
  font-weight: 600;
}
.header .right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header .user {
  color: #606266;
}
</style>
