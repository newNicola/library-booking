<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6" v-for="c in cards" :key="c.label">
        <el-card>
          <div class="stat">
            <div class="num">{{ c.value }}</div>
            <div class="label">{{ c.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getStats } from '../api'

const cards = ref([
  { label: '今日预约', value: '-' },
  { label: '累计预约', value: '-' },
  { label: '封禁中', value: '-' },
  { label: '累计封禁', value: '-' },
])

onMounted(async () => {
  try {
    const s = await getStats()
    cards.value[0].value = s.today_bookings
    cards.value[1].value = s.total_bookings
    cards.value[2].value = s.active_bans
    cards.value[3].value = s.total_bans
  } catch (_) { /* 拦截器已提示 */ }
})
</script>

<style scoped>
.stat {
  text-align: center;
  padding: 8px 0;
}
.stat .num {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}
.stat .label {
  margin-top: 6px;
  color: #909399;
}
</style>
