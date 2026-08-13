import { type AdherenciaDePatron, useAdherenciaPorPatron } from "../../api/consultas";
import { Consulta } from "../../components/estados";
import { useNombreDePatron } from "./patrones";

const porcentaje = (n: number) => `${Math.round(n * 100)}%`;

function Fila({ dato }: { dato: AdherenciaDePatron }) {
  const nombreDe = useNombreDePatron();
  const flojo = dato.completion_rate < 0.9;
  return (
    <li className="adherencia__fila">
      <span className={`adherencia__nombre${flojo ? " adherencia__nombre--flojo" : ""}`}>
        {nombreDe(dato.pattern)}
      </span>
      <span className="adherencia__pista">
        <span
          className={`adherencia__hecho${flojo ? " adherencia__hecho--flojo" : ""}`}
          style={{ width: porcentaje(dato.completion_rate) }}
        />
      </span>
      <span className="adherencia__cifra">{porcentaje(dato.completion_rate)}</span>
      {/* El denominador al lado del porcentaje, no en un tooltip: 0 de 15 y 0 de
          226 se dibujan igual y significan cosas opuestas. */}
      <span className="adherencia__base">de {dato.sets_planned}</span>
    </li>
  );
}

export function Adherencia({ atletaId }: { atletaId: string }) {
  const consulta = useAdherenciaPorPatron(atletaId);

  return (
    <section>
      <h3>Adherencia por patrón</h3>
      <Consulta
        consulta={consulta}
        que="la adherencia"
        vacio={{
          cuando: (filas) => filas.length === 0,
          motivo: "Este atleta todavía no tiene series prescritas.",
        }}
      >
        {(filas) => (
          <ul className="adherencia">
            {filas.map((dato) => (
              <Fila key={dato.pattern} dato={dato} />
            ))}
          </ul>
        )}
      </Consulta>
    </section>
  );
}
