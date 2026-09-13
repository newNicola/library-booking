<template>
  <el-card>
    <template #header>
      <div class="filter-bar">
        <span>预约日志</span>
        <div class="filters">
          <el-input v-model="query.user_id" placeholder="按学号筛选" clearable style="width: 160px" />
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始日期" end-placeholder="结束日期" style="width: 260px" />
          <el-button type="primary" @click="search">查询</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" stripe v-loading="loading" height="520">
      <el-table-column prop="created_at" label="上报时间" width="170" />
      <el-table-column label="谁" min-width="120">
        <template #default="{ row }">
          {{ row.user_name }}
          <div class="sub">{{ row.user_id }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="dept_name" label="学院" min-width="140" />
      <el-table-column label="哪里" min-width="140">
        <template #default="{ row }">
          {{ row.place_name }}
          <div class="sub">{{ row.floor }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="seat" label="座位" width="90" />
      <el-table-column label="时间段" width="200">
        <template #default="{ row }">
          {{ row.date }} {{ row.begin }}-{{ row.end }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="prev, pager, next, total" :total="total"
        :page-size="query.page_size" :current-page="query.page" @current-change="onPage" />
    </div>
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { getLogs } from '../api'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const dateRange = ref(null)
const query = reactive({ page: 1, page_size: 20, user_id: '' })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size, user_id: query.user_id }
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await getLogs(params)
    rows.value = data.rows
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function search() {
  query.page = 1
  load()
}

function onPage(p) {
  query.page = p
  load()
}
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.filters {
  display: flex;
  gap: 8px;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.sub {
  color: #909399;
  font-size: 12px;
}
</style>
