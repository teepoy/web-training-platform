import { computed, ref, watch, type MaybeRefOrGetter, toValue } from "vue";

export function useDefaultCreatorFilter(
  orgId: MaybeRefOrGetter<string | null | undefined>,
  userId: MaybeRefOrGetter<string | null | undefined>,
) {
  const creatorFilter = ref<string | null>(null);
  const initializedScope = ref<string | null>(null);
  const scope = computed(() => {
    const organization = toValue(orgId);
    const user = toValue(userId);
    return organization && user ? `${organization}:${user}` : null;
  });

  watch(
    scope,
    (nextScope) => {
      if (!nextScope) {
        creatorFilter.value = null;
        initializedScope.value = null;
        return;
      }
      if (initializedScope.value === nextScope) return;
      creatorFilter.value = toValue(userId) ?? null;
      initializedScope.value = nextScope;
    },
    { immediate: true, flush: "sync" },
  );

  const isReady = computed(() => scope.value !== null && initializedScope.value === scope.value);

  return { creatorFilter, isReady };
}
