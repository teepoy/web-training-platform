import {
  type Ref,
  type ShallowRef,
  type ComputedRef,
  shallowRef,
  computed,
} from "vue";
import type { InjectionKey } from "vue";

export interface Annotation<TId = string> {
  kind: string;
  ids: Set<TId>;
}

export interface DataNode<TId = string> {
  id: string;
  parentId: string | null;
  annotation: ShallowRef<Annotation<TId> | null>;
  child: ComputedRef<DataNode<TId> | null>;
  visibleAnnotations: ComputedRef<Annotation<TId>[]>;
  annotate: (kind: string, ids: TId[]) => void;
  clear: () => void;
}

export interface DataPipeline<
  TItem extends { id: string },
  TId = string,
> {
  rawItems: Ref<TItem[]>;
  register: (id: string, parentId?: string) => DataNode<TId>;
  getNode: (id: string) => DataNode<TId> | undefined;
  nodes: ShallowRef<Record<string, DataNode<TId>>>;
}

export const DATA_PIPELINE_KEY: InjectionKey<DataPipeline<any, any>> = Symbol("dataPipeline");

export function createDataPipeline<TItem extends { id: string }>(
  rawItems: Ref<TItem[]>,
): DataPipeline<TItem> {
  const nodes = shallowRef<Record<string, DataNode>>({});

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

    const child = computed<DataNode | null>(() => {
      const allNodes = nodes.value;
      for (const n of Object.values(allNodes)) {
        if (n.parentId === id) return n;
      }
      return null;
    });

    const visibleAnnotations = computed<Annotation[]>(() => {
      return walkChain(id);
    });

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
