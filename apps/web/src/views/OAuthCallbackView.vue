<template>
  <div class="auth-page">
    <n-card class="auth-card">
      <n-spin v-if="processing" size="large" />
      <n-result
        v-else-if="errorMessage"
        status="error"
        title="Authentication Failed"
        :description="errorMessage"
      >
        <template #footer>
          <n-button @click="router.push('/login')">Back to Login</n-button>
        </template>
      </n-result>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useOrgStore } from '../stores/org'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const orgStore = useOrgStore()

const processing = ref(true)
const errorMessage = ref<string | null>(null)

onMounted(async () => {
  const raw = route.query.token
  const token = Array.isArray(raw) ? raw[0] : raw

  if (!token) {
    errorMessage.value = 'No authentication token received. Please try logging in again.'
    processing.value = false
    return
  }

  try {
    await authStore.oauthLogin(token)
    await orgStore.fetchOrganizations()
    router.replace('/datasets')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'OAuth authentication failed'
    errorMessage.value = msg
    processing.value = false
  }
})
</script>

<style scoped>
.auth-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
}

.auth-card {
  width: 360px;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
}
</style>
