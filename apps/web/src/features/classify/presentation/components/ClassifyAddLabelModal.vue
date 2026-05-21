<script setup lang="ts">
import { NButton, NInput, NModal } from "naive-ui";
import { injectClassifyPage } from "../../application/useClassifyPage";

const page = injectClassifyPage();
</script>

<template>
  <n-modal
    v-model:show="page.showAddLabelModal.value"
    preset="dialog"
    title="Add New Label"
  >
    <n-input
      v-model:value="page.newLabelName.value"
      placeholder="Enter label name"
      @keyup.enter="page.addNewLabel"
    />
    <template #action>
      <n-button @click="page.showAddLabelModal.value = false">
        Cancel
      </n-button>
      <n-button
        type="primary"
        :loading="page.addLabelMutation.isPending.value"
        :disabled="!page.newLabelName.value.trim()"
        @click="page.addNewLabel"
      >
        Add
      </n-button>
    </template>
  </n-modal>
</template>
