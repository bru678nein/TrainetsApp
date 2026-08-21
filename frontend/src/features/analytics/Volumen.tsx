import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useVolumen } from "../../api/consultas";
import { Consulta } from "../../components/estados";
import { TODOS, patronesDe, porSemana } from "./agregacion";

const legible = (patron: string) => patron.replaceAll("_", " ");

export function Volumen({ atletaId }: { atletaId: string }) {
  const consulta = useVolumen(atletaId);
  const [patron, setPatron] = useState(TODOS);

  return (
    <section>
      <h3>¿Adónde se va el volumen?</h3>
      <p className="grafica__pie">Series prescritas contra hechas, semana a semana.</p>
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
              <select value={patron} onChange={(e) => setPatron(e.target.value)}>
                <option value={TODOS}>todos</option>
                {patronesDe(filas).map((p) => (
                  <option key={p} value={p}>
                    {legible(p)}
                  </option>
                ))}
              </select>
            </label>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={porSemana(filas, patron)}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip />
                <Legend />
                {/* Las dos series, siempre. Un gráfico que muestre sólo lo hecho
                    es lo que da cualquier app de registro: sin el plan al lado
                    no se puede ver dónde se despegó. */}
                <Bar dataKey="prescrito" fill="var(--prescrito)" stroke="var(--borde)" />
                <Bar dataKey="hecho" fill="var(--hecho)" />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </Consulta>
    </section>
  );
}
