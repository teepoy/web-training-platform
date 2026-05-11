import type { Meta, StoryObj } from "@storybook/vue3"
import { defineComponent, h, ref, onMounted, nextTick } from "vue"
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

/**
 * Wrapper that programmatically clicks the FAB to open the drawer on mount.
 * The component's `isOpen` is internal state; this is the only way to open
 * the drawer without modifying the component.
 */
const OpenDrawerWrapper = defineComponent({
  name: "OpenDrawerWrapper",
  props: {
    messages: { type: Array as () => readonly ChatEntry[], default: () => [] },
    status: { type: String as () => AgentChatStatus, default: "idle" },
  },
  setup(props) {
    const drawerRef = ref<InstanceType<typeof AgentChatDrawer> | null>(null)
    onMounted(async () => {
      await nextTick()
      const fab = document.querySelector(".acd-fab") as HTMLElement | null
      fab?.click()
    })
    return () =>
      h(
        "div",
        { style: "min-height: 600px; position: relative;" },
        [
          h(AgentChatDrawer, {
            ref: drawerRef,
            messages: props.messages,
            status: props.status,
          }),
        ],
      )
  },
})

const meta = {
  title: "web-ui/components/AgentChatDrawer",
  component: AgentChatDrawer,
  decorators: [
    () => ({
      template:
        '<div style="min-height: 600px; position: relative;"><story/></div>',
    }),
  ],
  args: {
    messages: [] as readonly ChatEntry[],
    status: "idle" as AgentChatStatus,
  },
} satisfies Meta<typeof AgentChatDrawer>

export default meta
type Story = StoryObj<typeof meta>

/** FAB visible, drawer closed — default idle state with no messages. */
export const FAB: Story = {}

/** Drawer open with three messages (user, action, assistant). */
export const Conversation: Story = {
  render: (args) =>
    h(OpenDrawerWrapper, {
      messages: args.messages as readonly ChatEntry[],
      status: (args.status ?? "idle") as AgentChatStatus,
    }),
  args: {
    messages,
    status: "idle",
  },
}

/** Streaming state: loading dots, abort button, input disabled. */
export const Streaming: Story = {
  render: (args) =>
    h(OpenDrawerWrapper, {
      messages: args.messages as readonly ChatEntry[],
      status: (args.status ?? "streaming") as AgentChatStatus,
    }),
  args: {
    messages,
    status: "streaming",
  },
}

/** Error state: messages visible, no streaming indicators. */
export const Error: Story = {
  render: (args) =>
    h(OpenDrawerWrapper, {
      messages: args.messages as readonly ChatEntry[],
      status: (args.status ?? "error") as AgentChatStatus,
    }),
  args: {
    messages,
    status: "error",
  },
}
