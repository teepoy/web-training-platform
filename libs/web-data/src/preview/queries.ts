import { useQuery, useMutation } from "@tanstack/vue-query";
import { computed } from "vue";
import {
  createPreviewSession,
  getPreviewSession,
  listPreviewItems,
  startPreviewPersist,
  getPreviewPersistStatus,
  type PreviewPersistScope,
} from "./api";
import { previewKeys } from "./keys";

export function usePreviewSessionQuery(sessionId: () => string | null) {
  return useQuery({
    queryKey: computed(() => {
      const id = sessionId();
      return id ? previewKeys.session(id) : previewKeys.all;
    }),
    queryFn: ({ queryKey }) => {
      const id = queryKey[2] as string;
      return getPreviewSession(id);
    },
    enabled: computed(() => !!sessionId()),
  });
}

export function usePreviewItemsQuery(
  sessionId: () => string,
  cursor: () => string | null,
  limit: () => number,
) {
  return useQuery({
    queryKey: computed(() =>
      previewKeys.items(sessionId(), cursor(), limit()),
    ),
    queryFn: ({ queryKey }) => {
      const id = (queryKey as readonly unknown[])[2] as string;
      const c = (queryKey as readonly unknown[])[3] as { cursor: string | null; limit: number };
      return listPreviewItems(id, c.cursor, c.limit);
    },
    enabled: computed(() => !!sessionId()),
  });
}

export function usePreviewPersistMutation() {
  return useMutation({
    mutationFn: ({
      sessionId,
      scope,
    }: {
      sessionId: string;
      scope: PreviewPersistScope;
    }) => startPreviewPersist(sessionId, scope),
  });
}

export function usePreviewPersistStatusQuery(sessionId: () => string) {
  return useQuery({
    queryKey: computed(() => previewKeys.persistStatus(sessionId())),
    queryFn: ({ queryKey }) => {
      const id = (queryKey as readonly unknown[])[2] as string;
      return getPreviewPersistStatus(id);
    },
    enabled: computed(() => !!sessionId()),
    refetchInterval: 2000,
  });
}
