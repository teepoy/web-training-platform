import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
import AgentChatDrawer from "./AgentChatDrawer.vue"
import type { ChatEntry, AgentChatStatus } from "../../types/components"

const messages: ChatEntry[] = [
  {
    id: "m1",
    role: "user",
    content: "Show me cat samples",
    timestamp: Date.now() - 60000,
  },
  {
    id: "m2",
    role: "action",
    tool: "apply-filter",
    content: "Filtered to 25 cat samples",
    timestamp: Date.now() - 59000,
  },
  {
    id: "m3",
    role: "assistant",
    content: "I've filtered to 25 cat samples.",
    timestamp: Date.now() - 58000,
  },
]

function mountDrawer(props: {
  messages: readonly ChatEntry[]
  status: AgentChatStatus
}) {
  return mount(AgentChatDrawer, { props })
}

describe("AgentChatDrawer", () => {
  it("shows FAB when idle with no messages", () => {
    const wrapper = mountDrawer({ messages: [], status: "idle" })

    expect(wrapper.find(".acd-fab").exists()).toBe(true)
    expect(wrapper.find(".acd").exists()).toBe(false)
  })

  it("renders messages in drawer when open", async () => {
    const wrapper = mountDrawer({ messages, status: "idle" })
    await wrapper.find(".acd-fab").trigger("click")
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain("Show me cat samples")
    expect(html).toContain("I've filtered to 25 cat samples.")
    expect(html).toContain("apply-filter")
    expect(html).toContain("Filtered to 25 cat samples")
  })

  it("shows abort button and loading dots when streaming", async () => {
    const wrapper = mountDrawer({ messages, status: "streaming" })
    await wrapper.find(".acd-fab").trigger("click")
    await nextTick()

    expect(wrapper.find(".acd-input__btn--abort").exists()).toBe(true)
    expect(wrapper.find(".acd-msg--loading").exists()).toBe(true)
  })

  it("shows no streaming indicators when error", async () => {
    const wrapper = mountDrawer({ messages, status: "error" })
    await wrapper.find(".acd-fab").trigger("click")
    await nextTick()

    // Error state: no abort button, no loading dots — differentiates from streaming.
    expect(wrapper.find(".acd-input__btn--abort").exists()).toBe(false)
    expect(wrapper.find(".acd-msg--loading").exists()).toBe(false)
    // Messages still render in error state.
    expect(wrapper.html()).toContain("Show me cat samples")
  })

  it("emits send when input submitted via Enter", async () => {
    const wrapper = mountDrawer({ messages: [], status: "idle" })
    await wrapper.find(".acd-fab").trigger("click")
    await nextTick()

    const textarea = wrapper.find(".acd-input__field")
    await textarea.setValue("Hello agent")
    await textarea.trigger("keydown", { key: "Enter", shiftKey: false })

    expect(wrapper.emitted("send")).toBeTruthy()
    expect(wrapper.emitted("send")?.[0]).toEqual(["Hello agent"])
  })
})
