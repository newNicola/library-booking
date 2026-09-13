<template>
  <el-card>
    <template #header>
      <div class="filter-bar">
        <span>封禁管理</span>
        <div class="filters">
          <el-input v-model="keyword" placeholder="按学号搜索" clearable style="width: 180px" @keyup.enter="search" />
          <el-button type="primary" @click="search">查询</el-button>
          <el-button type="danger" @click="openAdd">新增封禁</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" stripe v-loading="loading">
      <el-table-column prop="user_id" label="学号" width="160" />
      <el-table-column prop="reason" label="封禁原因" min-width="160" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'danger' : 'info'">{{ row.is_active ? '封禁中' : '已解封' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="到期时间" width="170">
        <template #default="{ row }">{{ row.expires_at || '永久' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170" />
      <el-table-column prop="created_by" label="操作人" width="100" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.is_active" link type="success" @click="unban(row)">解封</el-button>
          <el-button v-else link type="danger" @click="reban(row)">重新封禁</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="prev, pager, next, total" :total="total"
        :page-size="pageSize" :current-page="page" @current-change="onPage" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑封禁' : '新增封禁'" width="420px">
      <el-form label-width="90px">
        <el-form-item label="学号">
          <el-input v-model="form.user_id" :disabled="!!editing" placeholder="学生学号" />
        </el-form-item>
        <el-form-item label="封禁原因">
          <el-input v-model="form.reason" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker v-model="form.expires_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="留空表示永久封禁" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">确定</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getBans, addBan, updateBan } from '../api'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = reactive({ user_id: '', reason: '', expires_at: '' })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await getBans({ page: page.value, page_size: pageSize, keyword: keyword.value })
    rows.value = data.rows
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function onPage(p) {
  page.value = p
  load()
}

function openAdd() {
  editing.value = null
  form.user_id = ''
  form.reason = ''
  form.expires_at = ''
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  form.user_id = row.user_id
  form.reason = row.reason || ''
  form.expires_at = row.expires_at || ''
  dialogVisible.value = true
}

async function save() {
  if (!form.user_id.trim()) {
    ElMessage.warning('请输入学号')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateBan(editing.value.id, { reason: form.reason, expires_at: form.expires_at })
    } else {
      await addBan({ user_id: form.user_id.trim(), reason: form.reason, expires_at: form.expires_at })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function unban(row) {
  try {
    await ElMessageBox.confirm(`确定解封学号 ${row.user_id} 吗？`, '确认', { type: 'warning' })
  } catch (_) {
    return
  }
  await updateBan(row.id, { is_active: false })
  ElMessage.success('已解封')
  load()
}

async function reban(row) {
  await updateBan(row.id, { is_active: true })
  ElMessage.success('已重新封禁')
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
</style>
