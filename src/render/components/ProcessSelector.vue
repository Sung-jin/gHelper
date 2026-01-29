<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

const emit = defineEmits(['selected'])
const processes = ref<any[]>([])
const searchQuery = ref('')
const isLoading = ref(false)

const refresh = async () => {
  isLoading.value = true
  processes.value = await (window as any).electronAPI.getProcessList()
  isLoading.value = false
}

const filtered = computed(() => {
  return processes.value.filter(p =>
    p.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    p.pid.toString().includes(searchQuery.value)
  )
})

const select = (proc: any) => {
  emit('selected', proc)
}

onMounted(refresh)
</script>

<template>
  <div class="selector-container">
    <div class="search-bar">
      <input v-model="searchQuery" placeholder="프로세스 이름 또는 PID 검색..." />
      <button @click="refresh" :disabled="isLoading">🔄</button>
    </div>

    <div class="process-list">
      <div v-for="p in filtered" :key="p.pid" class="process-item" @click="select(p)">
        <span class="pid">[{{ p.pid }}]</span>
        <span class="name">{{ p.name }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.selector-container { max-width: 600px; margin: 0 auto; background: #222; padding: 20px; border-radius: 8px; }
.search-bar { display: flex; gap: 10px; margin-bottom: 15px; }
.search-bar input { flex: 1; padding: 8px; border-radius: 4px; border: 1px solid #444; background: #333; color: white; }
.process-list { height: 400px; overflow-y: auto; border: 1px solid #444; }
.process-item { padding: 10px; border-bottom: 1px solid #333; cursor: pointer; transition: 0.2s; }
.process-item:hover { background: #3d3d3d; }
.pid { color: #888; margin-right: 10px; font-family: monospace; }
</style>