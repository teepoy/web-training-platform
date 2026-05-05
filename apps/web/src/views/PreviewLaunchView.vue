<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NCard, NInput, NButton, NSpace, NSpin } from 'naive-ui'
import { createPreviewSession } from '../api'

const router = useRouter()
const message = useMessage()

const collectionRef = ref('')
const isLoading = ref(false)

async function handlePreview() {
  if (!collectionRef.value.trim()) {
    message.warning('Please enter a collection ref')
    return
  }
  isLoading.value = true
  try {
    const session = await createPreviewSession(collectionRef.value.trim())
    await router.push({ name: 'preview-classify', params: { sessionId: session.session_id } })
  } catch (err) {
    message.error('Failed to create preview session: ' + String(err))
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div style="display: flex; justify-content: center; padding: 48px 16px;">
    <NCard title="Preview Dataset" style="max-width: 480px; width: 100%;">
      <NSpace vertical size="large">
        <p style="color: var(--n-text-color-3); margin: 0;">
          Browse a remote dataset collection without importing it. You can persist it as a real dataset later.
        </p>
        <NInput
          v-model:value="collectionRef"
          placeholder="e.g. imagenet-1k-sample"
          :disabled="isLoading"
          @keyup.enter="handlePreview"
        />
        <NButton
          type="primary"
          :loading="isLoading"
          :disabled="!collectionRef.trim()"
          @click="handlePreview"
        >
          Preview
        </NButton>
      </NSpace>
    </NCard>
  </div>
</template>
