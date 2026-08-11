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

export type AdherenciaDePatron = {
  pattern: string;
  sets_planned: number;
  sets_done: number;
  completion_rate: number;
  in_range_rate: number;
  avg_rir_deviation: number | null;
};

/**
 * Adherence by movement pattern, already sorted worst-first by the API.
 *
 * The order is not re-derived here on purpose. It is part of the answer — it puts
 * the pattern being skipped at the top without anybody looking for it — and a
 * second sort in the browser is a second place for it to change.
 */
export function useAdherenciaPorPatron(atletaId: string) {
  const pedir = useApi();
  return useQuery({
    queryKey: ["adherencia", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/adherence/by-pattern`, signal) as Promise<
        AdherenciaDePatron[]
      >,
  });
}

export type VolumenSemanal = {
  week: number;
  pattern: string;
  sets_planned: number;
  sets_done: number;
  tonnage_kg: number;
};

export function useVolumen(atletaId: string) {
  const pedir = useApi();
  return useQuery({
    queryKey: ["volumen", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/volume`, signal) as Promise<VolumenSemanal[]>,
  });
}
