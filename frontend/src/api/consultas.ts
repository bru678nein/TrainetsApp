import { useQuery } from "@tanstack/react-query";

import { useApi } from "./useApi";

export type Atleta = { id: string; full_name: string; level: string | null };

/**
 * The coach's athletes.
 *
 * No filtering happens here, and that is the decision: which athletes a coach
 * sees is decided by the database — row level security for whose they are, and
 * the endpoint's own predicate for which states count as current. Repeating
 * either rule in the browser creates a second copy that drifts, and the copy
 * that drifts is always the one nobody remembers writing.
 */
export function useAtletas() {
  const pedir = useApi();
  return useQuery({
    queryKey: ["atletas"],
    queryFn: ({ signal }) => pedir("/api/athletes", signal) as Promise<Atleta[]>,
  });
}
