import type { ProgresionDeEjercicio } from "../../api/consultas";

/**
 * Which exercise to show first, out of the fifty-nine in the catalogue.
 *
 * The one with the most weeks logged, which is the closest thing to "the lift
 * this programme is about" that the data can answer on its own. Alphabetical
 * would open on whatever happens to start with A — usually an accessory nobody
 * is tracking.
 */
export function elMasSeguido(series: ProgresionDeEjercicio[]): string | undefined {
  let mejor: ProgresionDeEjercicio | undefined;
  let mejorConCarga = -1;
  for (const serie of series) {
    const conCarga = serie.points.filter((p) => p.load_kg !== null).length;
    if (conCarga > mejorConCarga) {
      mejor = serie;
      mejorConCarga = conCarga;
    }
  }
  return mejor?.exercise;
}
