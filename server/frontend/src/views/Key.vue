<template>
  <div>
    <el-card>
      <template #header>当前密钥</template>
      <div class="key-line">
        <span class="key-value">{{ key || '（未配置）' }}</span>
      </div>
      <el-divider />
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="新密钥">
          <el-input v-model="newKey" placeholder="输入新密钥" style="max-width: 400px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">修改密钥</el-button>
        </el-form-item>
      </el-form>
      <el-alert type="warning" :closable="false" title="修改后立即生效，旧密钥即刻失效，所有客户端需使用新密钥才能通过验证。" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getKey, updateKey } from '../api'

const key = ref('')
const newKey = ref('')
const loading = ref(false)

onMounted(loadKey)

async function loadKey() {
  try {
    const data = await getKey()
    key.value = data.key
  } catch (_) { /* 拦截器已提示 */ }
}

async function submit() {
  if (!newKey.value.trim()) {
    ElMessage.warning('请输入新密钥')
    return
  }
  try {
    await ElMessageBox.confirm('确定修改密钥吗？修改后旧密钥立即失效。', '确认', { type: 'warning' })
  } catch (_) {
    return
  }
  loading.value = true
  try {
    await updateKey(newKey.value.trim())
    ElMessage.success('密钥已修改')
    key.value = newKey.value.trim()
    newKey.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.key-value {
  font-family: monospace;
  font-size: 16px;
  word-break: break-all;
}
</style>
