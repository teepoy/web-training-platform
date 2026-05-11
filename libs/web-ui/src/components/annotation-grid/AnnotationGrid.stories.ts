import type { Meta, StoryObj } from "@storybook/vue3";
import AnnotationGrid from "./AnnotationGrid.vue";
import type { AnnotationGridItem } from "../../types/components";

const annotationItems: AnnotationGridItem[] = Array.from({ length: 15 }, (_, i) => ({
  id: `ann-${String(i).padStart(3, "0")}`,
  imageSrcs: [`https://picsum.photos/160/160?random=${i + 10}`],
  currentLabel: i % 3 === 0 ? "cat" : i % 3 === 1 ? "dog" : null,
  draftLabel: i % 5 === 0 ? "bird" : null,
  predictionLabel: i % 2 === 0 ? "cat" : "dog",
  predictionConfidence: Math.random() * 0.5 + 0.5,
  predictionId: `pred-${i}`,
  metadata: { filename: `img_${i}.jpg` },
}));

const labelSpace = ["cat", "dog", "bird", "fish", "rabbit"];

const meta = {
  title: "web-ui/components/AnnotationGrid",
  component: AnnotationGrid,
  render: (args) => ({
    components: { AnnotationGrid },
    setup: () => ({ args }),
    template:
      '<div style="height: 600px"><AnnotationGrid v-bind="args" /></div>',
  }),
  args: {
    items: annotationItems,
    totalCount: 15,
    labelSpace,
    thumbSize: 160,
    layout: "grid" as const,
    isLoading: false,
    submitting: false,
    readOnly: false,
  },
} satisfies Meta<typeof AnnotationGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const List: Story = {
  args: {
    layout: "list",
  },
};

export const Loading: Story = {
  args: {
    isLoading: true,
  },
};

export const ReadOnly: Story = {
  args: {
    readOnly: true,
  },
};
