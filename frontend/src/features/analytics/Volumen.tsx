import { useState } from "react";

import { useVolumen } from "../../api/consultas";
import { Consulta } from "../../components/estados";
import { TODOS, patronesDe, porSemana } from "./agregacion";

const legible = (patron: string) => patron.replaceAll("_", " ");

/**
 * Prescrito y hecho **superpuestos**, no uno al lado del otro.
 *
 * La columna hueca es lo planificado y la llena lo registrado, dibujada adentro.
 * Así el faltante es el hueco que queda arriba: se lee de un vistazo y sin
 * leyenda, porque no hay dos alturas que comparar sino una que no llegó.
 *
 * Se dibuja a mano y no con la librería de gráficos por eso mismo: dos series
 * agrupadas es lo que sale por defecto, superponerlas hay que pelearlo, y lo que
 * se gana —tooltip, ejes— no hace falta cuando las cifras están escritas abajo.
 *
 * Una semana sin nada prescrito no se dibuja como cero: no se dibuja. Cero
 * prescrito y cero hecho es una semana que no existe, no una que se saltearon.
 */
function Columnas({
  puntos,
}: {
  puntos: { week: number; prescrito: number; hecho: number }[];
}) {
  const techo = Math.max(1, ...puntos.map((p) => p.prescrito));
  return (
    <ul className="columnas">
      {puntos.map((p) => (
        <li key={p.week} className="columnas__semana">
          <div
            className="columnas__prescrito"
            style={{ height: `${(p.prescrito / techo) * 100}%` }}
            role="img"
            aria-label={`Semana ${p.week}: ${p.hecho} de ${p.prescrito} series`}
          >
            <span
              className="columnas__hecho"
              style={{
                height: `${p.prescrito ? (p.hecho / p.prescrito) * 100 : 0}%`,
              }}
            />
          </div>
          <span className="columnas__cifra numeros" aria-hidden="true">
            {p.hecho}/{p.prescrito}
          </span>
          <span className="columnas__etiqueta numeros" aria-hidden="true">
            {p.week}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Volumen({ atletaId }: { atletaId: string }) {
  const consulta = useVolumen(atletaId);
  const [patron, setPatron] = useState(TODOS);

  return (
    <section>
      <h3>¿Adónde se va el volumen?</h3>
      <p className="grafica__pie">
        Series prescritas contra hechas, semana a semana.
      </p>
      <Consulta
        consulta={consulta}
        que="el volumen"
        vacio={{
          cuando: (filas) => filas.length === 0,
          motivo: "Este atleta todavía no tiene series prescritas.",
        }}
      >
        {(filas) => (
          <>
            <label>
              Patrón{" "}
              <select
                value={patron}
                onChange={(e) => setPatron(e.target.value)}
              >
                <option value={TODOS}>todos</option>
                {patronesDe(filas).map((p) => (
                  <option key={p} value={p}>
                    {legible(p)}
                  </option>
                ))}
              </select>
            </label>
            <Columnas puntos={porSemana(filas, patron)} />
          </>
        )}
      </Consulta>
    </section>
  );
}
