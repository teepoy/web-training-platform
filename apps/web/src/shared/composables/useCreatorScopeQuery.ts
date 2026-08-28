import { computed, toValue, type MaybeRefOrGetter } from "vue";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";

export type CreatorScope = "me" | "all" | (string & {});

function firstQueryValue(value: unknown): string | undefined {
  if (Array.isArray(value)) return typeof value[0] === "string" ? value[0] : undefined;
  return typeof value === "string" ? value : undefined;
}

export function useCreatorScopeQuery(
  orgId: MaybeRefOrGetter<string | null | undefined>,
  userId: MaybeRefOrGetter<string | null | undefined>,
  options: { queryKey?: string; defaultScope?: "me" | "all" } = {},
) {
  const route = useRoute();
  const router = useRouter();
  const queryKey = options.queryKey ?? "creator";
  const defaultScope = options.defaultScope ?? "me";

  const creatorScope = computed<CreatorScope>({
    get: () => firstQueryValue(route.query[queryKey]) || defaultScope,
    set: (value) => {
      const query: LocationQueryRaw = { ...route.query };
      if (value === defaultScope) delete query[queryKey];
      else query[queryKey] = value;
      void router.replace({ query });
    },
  });

  const creatorId = computed<string | null>(() => {
    if (creatorScope.value === "all") return null;
    if (creatorScope.value === "me") return toValue(userId) ?? null;
    return creatorScope.value;
  });

  const isReady = computed(
    () => !!toValue(orgId) && (creatorScope.value !== "me" || typeof toValue(userId) === "string"),
  );

  return { creatorScope, creatorId, isReady };
}
