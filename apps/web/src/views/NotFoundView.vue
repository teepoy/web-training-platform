<template>
  <div style="display: flex; justify-content: center; align-items: center; min-height: 60vh">
    <n-result
      status="404"
      title="404 - Page Not Found"
      description="The page you are looking for does not exist or has been moved."
    >
      <template #footer>
        <n-button type="primary" @click="router.push('/')">Back to Home</n-button>
      </template>
    </n-result>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>
