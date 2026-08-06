export type QueryBuilderCombinator = "and" | "or";

export interface QueryBuilderRule<TValue> {
  kind: "rule";
  id: string;
  value: TValue;
}

export interface QueryBuilderGroup<TValue> {
  kind: "group";
  id: string;
  combinator: QueryBuilderCombinator;
  items: Array<QueryBuilderRule<TValue> | QueryBuilderGroup<TValue>>;
}

export type QueryBuilderNode<TValue> = QueryBuilderRule<TValue> | QueryBuilderGroup<TValue>;

export function createQueryBuilderId(): string {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (!randomUuid) throw new Error("The browser cannot create a QueryBuilder node ID");
  return randomUuid.call(globalThis.crypto);
}

export function createQueryBuilderGroup<TValue>(
  combinator: QueryBuilderCombinator = "and",
): QueryBuilderGroup<TValue> {
  return {
    kind: "group",
    id: createQueryBuilderId(),
    combinator,
    items: [],
  };
}

export function isQueryBuilderGroup<TValue>(
  node: QueryBuilderNode<TValue>,
): node is QueryBuilderGroup<TValue> {
  return node.kind === "group";
}
