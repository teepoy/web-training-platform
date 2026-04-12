<!--
  AgentChatDrawer — floating chat drawer for the classify agent.

  Mounts at the bottom-right of the viewport.  Toggled by a floating
  action button.  Contains a scrollable message list and an input bar.
-->
<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { ChatEntry } from '../types'
import type { AgentChatStatus } from '../composables/useAgentChat'

const props = defineProps<{
  messages: readonly ChatEntry[]
  status: AgentChatStatus
}>()

const emit = defineEmits<{
  send: [message: string]
  abort: []
  clear: []
}>()

const isOpen = ref(false)
const inputText = ref('')
const scrollRef = ref<HTMLElement | null>(null)

function toggle() {
  isOpen.value = !isOpen.value
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  inputText.value = ''
  emit('send', text)
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const isStreaming = computed(() => props.status === 'streaming')

// Auto-scroll to bottom on new messages
watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  },
)

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <!-- Floating action button -->
  <button
    v-if="!isOpen"
    class="acd-fab"
    @click="toggle"
    title="Open Agent Chat"
  >
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  </button>

  <!-- Drawer panel -->
  <Transition name="acd-slide">
    <div v-if="isOpen" class="acd">
      <!-- Header -->
      <div class="acd-header">
        <span class="acd-header__title">Agent Chat</span>
        <div class="acd-header__actions">
          <button class="acd-header__btn" @click="emit('clear')" title="Clear history">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </button>
          <button class="acd-header__btn" @click="toggle" title="Close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Messages -->
      <div ref="scrollRef" class="acd-messages">
        <div v-if="messages.length === 0" class="acd-messages__empty">
          Ask the agent to analyze your data, create charts, or explore metadata.
        </div>
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="acd-msg"
          :class="`acd-msg--${msg.role}`"
        >
          <div v-if="msg.role === 'action'" class="acd-msg__action">
            <span class="acd-msg__tool">{{ msg.tool }}</span>
            <span class="acd-msg__summary">{{ msg.content }}</span>
          </div>
          <template v-else>
            <div class="acd-msg__bubble">{{ msg.content }}</div>
            <div class="acd-msg__time">{{ formatTime(msg.timestamp) }}</div>
          </template>
        </div>
        <div v-if="isStreaming" class="acd-msg acd-msg--loading">
          <div class="acd-msg__dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

      <!-- Input bar -->
      <div class="acd-input">
        <textarea
          v-model="inputText"
          class="acd-input__field"
          placeholder="Ask the agent..."
          rows="1"
          @keydown="handleKeyDown"
          :disabled="isStreaming"
        />
        <button
          v-if="isStreaming"
          class="acd-input__btn acd-input__btn--abort"
          @click="emit('abort')"
          title="Stop"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        </button>
        <button
          v-else
          class="acd-input__btn"
          @click="handleSend"
          :disabled="!inputText.trim()"
          title="Send"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* Floating Action Button */
.acd-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #5b6abf;
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  transition: transform 0.15s, box-shadow 0.15s;
}
.acd-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* Drawer */
.acd {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1001;
  width: 380px;
  max-height: 520px;
  display: flex;
  flex-direction: column;
  background: #1e1e2e;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

/* Slide transition */
.acd-slide-enter-active,
.acd-slide-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.acd-slide-enter-from,
.acd-slide-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(0.96);
}

/* Header */
.acd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.acd-header__title {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
.acd-header__actions {
  display: flex;
  gap: 4px;
}
.acd-header__btn {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.45);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.acd-header__btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
}

/* Messages */
.acd-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}
.acd-messages__empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  text-align: center;
  padding: 40px 16px;
  line-height: 1.5;
}

/* Message bubbles */
.acd-msg {
  max-width: 90%;
}
.acd-msg--user {
  align-self: flex-end;
}
.acd-msg--assistant {
  align-self: flex-start;
}
.acd-msg--action {
  align-self: center;
  max-width: 100%;
}
.acd-msg__bubble {
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 12px;
  border-radius: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}
.acd-msg--user .acd-msg__bubble {
  background: #5b6abf;
  color: #fff;
  border-bottom-right-radius: 2px;
}
.acd-msg--assistant .acd-msg__bubble {
  background: rgba(255, 255, 255, 0.07);
  color: rgba(255, 255, 255, 0.85);
  border-bottom-left-radius: 2px;
}
.acd-msg__time {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.25);
  margin-top: 2px;
}
.acd-msg--user .acd-msg__time {
  text-align: right;
}

/* Action badge */
.acd-msg__action {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.acd-msg__tool {
  font-family: monospace;
  font-size: 10px;
  color: #7c8aff;
  background: rgba(124, 138, 255, 0.12);
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}
.acd-msg__summary {
  color: rgba(255, 255, 255, 0.55);
}

/* Loading dots */
.acd-msg--loading {
  align-self: flex-start;
}
.acd-msg__dots {
  display: flex;
  gap: 4px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.07);
  border-radius: 10px;
}
.acd-msg__dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.4);
  animation: acd-dot-bounce 1.2s ease-in-out infinite;
}
.acd-msg__dots span:nth-child(2) { animation-delay: 0.15s; }
.acd-msg__dots span:nth-child(3) { animation-delay: 0.3s; }

@keyframes acd-dot-bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
}

/* Input bar */
.acd-input {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.acd-input__field {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  color: #fff;
  font-size: 12px;
  padding: 8px 10px;
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: 1.4;
  max-height: 80px;
}
.acd-input__field::placeholder {
  color: rgba(255, 255, 255, 0.3);
}
.acd-input__field:focus {
  border-color: rgba(91, 106, 191, 0.5);
}
.acd-input__btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #5b6abf;
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity 0.15s;
}
.acd-input__btn:disabled {
  opacity: 0.3;
  cursor: default;
}
.acd-input__btn:not(:disabled):hover {
  opacity: 0.85;
}
.acd-input__btn--abort {
  background: #c0392b;
}
</style>
