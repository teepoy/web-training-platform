<template>
  <div class="auth-page">
    <n-card class="auth-card" title="Create Account">
      <n-form ref="formRef" :model="formData" :rules="rules" @keyup.enter="handleSubmit">
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formData.name"
            type="text"
            placeholder="Your name"
            :disabled="loading"
          />
        </n-form-item>
        <n-form-item label="Email" path="email">
          <n-input
            v-model:value="formData.email"
            type="text"
            placeholder="you@example.com"
            :disabled="loading"
          />
        </n-form-item>
        <n-form-item label="Password" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            placeholder="Password"
            show-password-on="click"
            :disabled="loading"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleSubmit"
        >
          Create Account
        </n-button>
      </n-form>
      <div class="auth-link">
        Already have an account?
        <router-link to="/login">Login</router-link>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, type FormInst, type FormRules } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

import { useOrgStore } from '../stores/org'
const orgStore = useOrgStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)

const formData = ref({
  name: '',
  email: '',
  password: '',
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  email: [{ required: true, message: 'Email is required', trigger: 'blur' }],
  password: [{ required: true, message: 'Password is required', trigger: 'blur' }],
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authStore.register(formData.value.name, formData.value.email, formData.value.password)
    await orgStore.fetchOrganizations()
    router.push('/datasets')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Registration failed'
    message.error(msg)
  } finally {
    loading.value = false
  }
}
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

.auth-link {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
}
</style>
