<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { NInput, NButton, NSpace, NAlert } from 'naive-ui'
import { createPreviewSession } from '@platform/web-data/preview'
import type { PreviewLauncherRequiredProps } from '@platform/widget-sdk'

const props = defineProps<PreviewLauncherRequiredProps>()

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
    props.onComplete({ sessionId: session.session_id })
  } catch (err) {
    message.error('Failed to create preview session: ' + String(err))
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <NSpace vertical size="large">
    <NAlert type="info" :show-icon="false" style="margin-bottom: 8px">
      Browse a remote dataset collection without importing it. You can persist it as a real dataset later.
    </NAlert>
    <NInput
      v-model:value="collectionRef"
      placeholder="e.g. imagenet-1k-sample"
      :disabled="isLoading"
      @keyup.enter="handlePreview"
    />
    <NSpace>
      <NButton
        type="primary"
        :loading="isLoading"
        :disabled="!collectionRef.trim()"
        @click="handlePreview"
      >
        Preview
      </NButton>
      <NButton
        secondary
        :disabled="isLoading"
        @click="collectionRef = 'imagenet-1k-sample'"
      >
        Use mock
      </NButton>
    </NSpace>
  </NSpace>
</template>
