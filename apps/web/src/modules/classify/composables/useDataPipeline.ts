import {
  type ComputedRef,
  type Ref,
  type ShallowRef,
  computed,
  shallowRef,
} from "vue";
import type { InjectionKey } from "vue";
import type { Annotation, BrowserItem, DataNode, DataPipeline } from "../types";

export const DATA_PIPELINE_KEY: InjectionKey<DataPipeline<BrowserItem>> =
  Symbol("dataPipeline");

export function createDataPipeline<TItem extends { id: string }>(
  rawItems: Ref<TItem[]>,
): DataPipeline<TItem> {
  const nodes: ShallowRef<Record<string, DataNode>> = shallowRef({});

  function walkChain(nodeId: string): Annotation[] {
    const visited = new Set<string>();
    const annotations: Annotation[] = [];
    let currentId: string | null = nodeId;

    while (currentId && !visited.has(currentId)) {
      visited.add(currentId);
      const node: DataNode | undefined = nodes.value[currentId];
      if (node?.annotation.value) {
        annotations.push(node.annotation.value);
      }
      currentId = node?.parentId ?? null;
    }

    return annotations;
  }

  function register(id: string, parentId?: string): DataNode {
    const annotation = shallowRef<Annotation | null>(null);

    const child: ComputedRef<DataNode | null> = computed(() => {
      const allNodes = nodes.value;
      for (const n of Object.values(allNodes)) {
        if (n.parentId === id) return n;
      }
      return null;
    });

    const visibleAnnotations = computed<Annotation[]>(() => walkChain(id));

    const node: DataNode = {
      id,
      parentId: parentId ?? null,
      annotation,
      child,
      visibleAnnotations,
      annotate(kind: string, ids: string[]) {
        annotation.value = { kind, ids: new Set(ids) };
      },
      clear() {
        annotation.value = null;
      },
    };

    nodes.value = { ...nodes.value, [id]: node };
    return node;
  }

  function getNode(id: string): DataNode | undefined {
    return nodes.value[id];
  }

  return {
    rawItems,
    register,
    getNode,
    nodes,
  };
}
